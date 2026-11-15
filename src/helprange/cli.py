"""``helprange`` – command-line client for the HelpRange API (stdlib argparse; installed with the package).

    helprange login                       store an API key in ~/.config/helprange/config (0600)
    helprange share deck.pdf --to anna@acme.com --expires 2026-12-31 --no-download --watermark
    helprange documents [--folder ID]
    helprange links [--document ID] [--folder ID] [--room ID] [--status active|expired|disabled|all] [--label TEXT]
    helprange views --link LINK_ID | views DOCUMENT_ID
    helprange rooms create NAME [--folder NAME ...] [--nda] [--invite EMAIL ...] | delete ROOM --yes
    helprange rooms list | show ROOM | index ROOM | documents ROOM | add ROOM DOC... | guests ROOM
    helprange rooms invite ROOM EMAIL... | questions ROOM

Every command takes --json (machine-readable output for scripts and agents). The key comes from --api-key, then
HELPRANGE_API_KEY, then the config file.
"""
from __future__ import annotations

import argparse
import getpass
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence

from ._client import HelpRange
from ._errors import AuthenticationError, HelpRangeError
from ._generated.models import CreateDataRoomBodySettings
from ._version import __version__

URL_RE = re.compile(r"^https?://", re.I)


# ------------------------------------------------------------------------------------------------ config

def config_path() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    return Path(base) / "helprange" / "config"


def read_config() -> Dict[str, Any]:
    path = config_path()
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


def write_config(data: Dict[str, Any]) -> Path:
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(path.parent, 0o700)
    except OSError:
        pass
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as fh:
        json.dump(data, fh, indent=2)
        fh.write("\n")
    os.chmod(path, 0o600)  # also when the file existed with wider permissions
    return path


def resolve_key(args: argparse.Namespace) -> Optional[str]:
    return args.api_key or os.environ.get("HELPRANGE_API_KEY") or read_config().get("api_key")


def make_client(args: argparse.Namespace) -> HelpRange:
    key = resolve_key(args)
    if not key:
        raise CLIError("No API key. Run `helprange login`, set HELPRANGE_API_KEY or pass --api-key.")
    base_url = args.base_url or os.environ.get("HELPRANGE_BASE_URL") or read_config().get("base_url")
    return HelpRange(key, base_url=base_url)


class CLIError(Exception):
    pass


# ------------------------------------------------------------------------------------------------ output

def emit(args: argparse.Namespace, data: Any, human: Callable[[], None]) -> None:
    if args.json:
        json.dump(data, sys.stdout, indent=2, ensure_ascii=False)
        sys.stdout.write("\n")
    else:
        human()


def table(rows: Iterable[Sequence[Any]], headers: Sequence[str]) -> None:
    rows = [["" if c is None else str(c) for c in r] for r in rows]
    if not rows:
        print("(none)")
        return
    widths = [max(len(h), *(len(r[i]) for r in rows)) for i, h in enumerate(headers)]
    print("  ".join(h.ljust(w) for h, w in zip(headers, widths)).rstrip())
    for r in rows:
        print("  ".join(c.ljust(w) for c, w in zip(r, widths)).rstrip())


# ------------------------------------------------------------------------------------------------ commands

def cmd_login(args: argparse.Namespace) -> int:
    key = args.key
    if not key:
        if sys.stdin.isatty():
            key = getpass.getpass("HelpRange API key (Settings → API keys, hr_live_… or hr_test_…): ")
        else:
            key = sys.stdin.readline()
    key = (key or "").strip()
    if not key:
        raise CLIError("No key given.")
    me: Dict[str, Any] = {}
    if not args.no_verify:
        client = HelpRange(key, base_url=args.base_url)
        try:
            me = dict(client.account.me())
        except AuthenticationError as exc:
            raise CLIError(f"The key was refused: {exc.message}") from exc
        except HelpRangeError as exc:
            if exc.status not in (402, 403):  # a key without team:read or on a plan without the API is still a key
                raise
    data = read_config()
    data["api_key"] = key
    if args.base_url:
        data["base_url"] = args.base_url
    path = write_config(data)
    mode = "test mode (sandbox)" if key.startswith("hr_test_") else "live"
    result = {"saved_to": str(path), "mode": mode, "email": me.get("email"), "team": me.get("team")}

    def human() -> None:
        who = f" as {me.get('email')}" + (f" ({me.get('team')})" if me.get("team") else "") if me else ""
        print(f"Logged in{who} – {mode}. Key saved to {path} (readable only by you).")

    emit(args, result, human)
    return 0


def cmd_logout(args: argparse.Namespace) -> int:
    data = read_config()
    data.pop("api_key", None)
    write_config(data)
    emit(args, {"logged_out": True}, lambda: print(f"Removed the API key from {config_path()}."))
    return 0


def cmd_whoami(args: argparse.Namespace) -> int:
    client = make_client(args)
    me = client.account.me()
    emit(args, me, lambda: print(f"{me.get('name') or ''} <{me.get('email')}> · team {me.get('team')} · plan {me.get('plan')}"
                                 f" · {'test mode' if client.test_mode else 'live'}"))
    return 0


def cmd_share(args: argparse.Namespace) -> int:
    client = make_client(args)
    upload: Dict[str, Any] = {"folder_id": args.folder}
    if URL_RE.match(args.file):
        upload["file_url"] = args.file
        if args.filename:
            upload["filename"] = args.filename
    else:
        path = Path(args.file).expanduser()
        if not path.is_file():
            raise CLIError(f"No such file: {args.file}")
        upload["file"] = path
        upload["filename"] = args.filename or path.name
    settings: Dict[str, Any] = {
        "expires_on": args.expires,
        "allow_download": False if args.no_download else None,
        "watermark": True if args.watermark else None,
        "require_email": True if args.require_email else None,
        "passcode": args.passcode,
    }
    if args.views_limit is not None:
        settings["views_limit"] = args.views_limit
    document = client.documents.upload(**upload)
    # One link per recipient: the label says who it is for, so the statistics show who opened what.
    labels: List[Optional[str]] = list(args.to) if args.to else [args.label]
    links = [client.documents.create_link(document["id"], label=label, **settings) for label in labels]
    result = {"document": document, "links": links}

    def human() -> None:
        print(f"Uploaded {document['name']} (id {document['id']}){' – test mode' if client.test_mode else ''}")
        for link in links:
            print(f"{link['label']}: {link['url']}" if args.to else link["url"])
        if args.to:
            print("Send each person their own link – HelpRange does not e-mail share links created through the API.",
                  file=sys.stderr)

    emit(args, result, human)
    return 0


def cmd_documents(args: argparse.Namespace) -> int:
    res = make_client(args).documents.list(folder_id=args.folder)
    emit(args, res, lambda: table(((d["id"], d["name"], d.get("path", ""), d.get("pages"), d.get("default_link"))
                                   for d in res["documents"]), ["ID", "NAME", "FOLDER", "PAGES", "DEFAULT LINK"]))
    return 0


def cmd_links(args: argparse.Namespace) -> int:
    res = make_client(args).links.list(document_id=args.document, folder_id=args.folder, room_id=args.room,
                                       status=args.status, label=args.label, page=args.page, limit=args.limit)

    def human() -> None:
        table(((lk["id"], lk["document"], lk["label"], lk["status"], lk["views"], lk["expires_on"] or "", lk["url"])
               for lk in res["links"]), ["ID", "DOCUMENT", "LABEL", "STATUS", "VIEWS", "EXPIRES", "URL"])
        if res.get("next_page"):
            print(f"Page {res['page']} of {res['total']} links – next: --page {res['next_page']}", file=sys.stderr)

    emit(args, res, human)
    return 0


VIEW_HEADERS = ["OPENED", "VIEWER", "SECONDS", "PAGES", "COUNTRY", "DOWNLOADED"]


def _view_row(v: Any) -> List[Any]:
    return [v["opened_at"], v["viewer"], v["seconds_read"], v.get("pages_read", ""), v["country"],
            "yes" if v["downloaded"] else ""]


def cmd_views(args: argparse.Namespace) -> int:
    client = make_client(args)
    if args.link is not None:
        res = client.links.views(args.link, page=args.page, limit=args.limit)

        def human_link() -> None:
            link = res["link"]
            print(f"{link['document']} – link \"{link['label']}\" ({link['url']}): {res['total']} views")
            table((_view_row(v) for v in res["views"]), VIEW_HEADERS)
            if res.get("next_page"):
                print(f"More: --page {res['next_page']}", file=sys.stderr)

        emit(args, res, human_link)
        return 0
    if args.document_id is None:
        raise CLIError("Pass a DOCUMENT_ID or --link LINK_ID (link ids: `helprange links --document DOCUMENT_ID`).")
    doc = client.documents.get(args.document_id, recent_views=min(args.limit, 100))

    def human() -> None:
        print(f"{doc['name']}: {doc['views']} views, {doc['downloads']} downloads, "
              f"{doc.get('total_seconds_read') or 0} s read in total")
        table((_view_row(v) for v in doc["recent_views"]), VIEW_HEADERS)

    emit(args, doc, human)
    return 0


def cmd_rooms(args: argparse.Namespace) -> int:
    client = make_client(args)
    rooms = client.data_rooms
    action = args.rooms_cmd
    res: Any
    if action == "create":
        settings: CreateDataRoomBodySettings = {}
        if args.nda_id is not None:
            settings["nda_id"] = args.nda_id
        elif args.nda:
            settings["nda"] = True
        if args.expires:
            settings["expires_on"] = args.expires
        if args.download:
            settings["download"] = True
        room = rooms.create(name=args.name, folders=args.folders or None, settings=settings or None)
        guests = [rooms.guests.invite(room["id"], email=e, send_invite=False if args.no_email else None)
                  for e in args.invite or []]
        res = {"data_room": room, "guests": guests}

        def human_create() -> None:
            print(f"Created data room {room['name']} (id {room['id']}){' – test mode' if client.test_mode else ''}")
            if room.get("folders"):
                print("Folders: " + ", ".join(f["name"] for f in room["folders"]))
            if room.get("nda_required"):
                print(f"NDA: {room['nda_required']}")
            print(f"Guest link: {room['links']['guest_link']}")
            for g in guests:
                print(f"{g['email']}: {g['link']}" + (" (already a guest)" if g.get("already_a_guest") else ""))

        emit(args, res, human_create)
    elif action == "delete":
        if not args.yes:
            raise CLIError(f"Deleting data room {args.room_id} removes it and every guest's access. "
                           "Run again with --yes to confirm.")
        res = rooms.delete(args.room_id, confirm=True)
        emit(args, res, lambda: print(f"Deleted data room {res.get('name', '')} (id {res['id']})."))
    elif action == "guests":
        res = rooms.guests.list(args.room_id)
        emit(args, res, lambda: table(((g["id"], g["email"], g.get("nda", ""), g["link"]) for g in res["guests"]),
                                      ["ID", "EMAIL", "NDA", "LINK"]))
    elif action == "list":
        res = rooms.list()
        emit(args, res, lambda: table(((r["id"], r["name"], r["guests"], r["documents"], r["pending_access_requests"],
                                        "frozen" if r["frozen"] else "") for r in res["data_rooms"]),
                                      ["ID", "NAME", "GUESTS", "DOCUMENTS", "ACCESS REQUESTS", ""]))
    elif action == "show":
        res = rooms.get(args.room_id)

        def human() -> None:
            print(f"{res['name']} (id {res['id']})" + (f" · expires {res['expires_at']}" if res.get("expires_at") else ""))
            print(f"\nGuests ({len(res['guests'])}):")
            table(([g.get("email"), g.get("nda", "")] for g in res["guests"]), ["EMAIL", "NDA"])
            print(f"\nDocuments ({len(res['documents'])}):")
            table(([d.get("id"), d.get("name")] for d in res["documents"]), ["ID", "NAME"])

        emit(args, res, human)
    elif action == "index":
        res = rooms.get_index(args.room_id)

        def walk(nodes: Any, depth: int = 0) -> None:
            for n in nodes:
                print(f"{'  ' * depth}{n.get('number', '')} {n.get('name') or n.get('title') or ''}".rstrip())
                walk(n.get("children") or [], depth + 1)

        emit(args, res, lambda: walk(res["index"]))
    elif action == "documents":
        res = rooms.documents.list(args.room_id)
        emit(args, res, lambda: table(((d["number"], d["document_id"], d["name"], d.get("room_folder") or "", d["approval"])
                                       for d in res["documents"]), ["NO.", "DOC ID", "NAME", "ROOM FOLDER", "STATUS"]))
    elif action == "add":
        res = rooms.documents.add(args.room_id, document_ids=args.document_ids, folder_id=args.folder)
        emit(args, res, lambda: print(f"Added {len(args.document_ids)} document(s) to data room {args.room_id}."))
    elif action == "invite":
        results = [rooms.guests.invite(args.room_id, email=e) for e in args.emails]

        def human() -> None:
            for r in results:
                print(f"{r['email']}: {'already a guest' if r.get('already_a_guest') else 'invited'} – {r.get('link', '')}")

        emit(args, results, human)
    elif action == "questions":
        res = rooms.questions.list(args.room_id, status=args.status)
        emit(args, res, lambda: table(((q["number"], q["status"], q["category"], q["text"][:80]) for q in res["questions"]),
                                      ["NO.", "STATUS", "CATEGORY", "QUESTION"]))
    return 0


# ------------------------------------------------------------------------------------------------ parser

def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--json", action="store_true", default=argparse.SUPPRESS, help="print JSON (for scripts and agents)")
    common.add_argument("--api-key", default=argparse.SUPPRESS, help="API key (default: HELPRANGE_API_KEY, then the saved key)")
    common.add_argument("--base-url", default=argparse.SUPPRESS, help=argparse.SUPPRESS)

    p = argparse.ArgumentParser(prog="helprange", parents=[common], description="HelpRange from the command line.",
                                epilog="Docs: https://www.helprange.com/developers")
    p.add_argument("--version", action="version", version=f"helprange {__version__}")
    sub = p.add_subparsers(dest="command", metavar="COMMAND")
    sub.required = True

    s = sub.add_parser("login", parents=[common], help="save an API key (~/.config/helprange/config, mode 0600)")
    s.add_argument("--key", help="the key (default: prompt, or read one line from stdin)")
    s.add_argument("--no-verify", action="store_true", help="save without checking the key against the API")
    s.set_defaults(func=cmd_login)

    sub.add_parser("logout", parents=[common], help="forget the saved key").set_defaults(func=cmd_logout)
    sub.add_parser("whoami", parents=[common], help="who the key acts as").set_defaults(func=cmd_whoami)

    s = sub.add_parser("share", parents=[common], help="upload a file and print a share link",
                       description="Upload FILE (a path or a public http(s) URL) and create a tracked share link. "
                                   "With --to, one link per recipient, labelled with their e-mail. "
                                   "HelpRange does not e-mail these links – send them yourself.")
    s.add_argument("file", metavar="FILE")
    s.add_argument("--to", action="append", metavar="EMAIL", help="recipient; repeat for several (one link each)")
    s.add_argument("--expires", metavar="YYYY-MM-DD", help="last day the link works")
    s.add_argument("--no-download", action="store_true", help="block download and print")
    s.add_argument("--watermark", action="store_true", help="watermark pages with the viewer's e-mail")
    s.add_argument("--require-email", action="store_true", help="viewers enter their e-mail before opening")
    s.add_argument("--passcode", help="password viewers must enter")
    s.add_argument("--views-limit", type=int, metavar="N", help="maximum number of views")
    s.add_argument("--label", help="link label (default: date and time; ignored with --to)")
    s.add_argument("--folder", type=int, metavar="FOLDER_ID", help="target folder (default: your default folder)")
    s.add_argument("--filename", help="file name to store (default: the file's name)")
    s.set_defaults(func=cmd_share)

    s = sub.add_parser("documents", parents=[common], help="list documents")
    s.add_argument("--folder", type=int, metavar="FOLDER_ID")
    s.set_defaults(func=cmd_documents)

    s = sub.add_parser("links", parents=[common], help="list share links (all of the team, or filtered)")
    s.add_argument("--document", type=int, metavar="DOCUMENT_ID", help="only links of this document")
    s.add_argument("--folder", type=int, metavar="FOLDER_ID", help="only links of documents in this folder")
    s.add_argument("--room", type=int, metavar="ROOM_ID", help="only links of this data room")
    s.add_argument("--status", choices=["active", "expired", "disabled", "all"], help="default: active")
    s.add_argument("--label", help="label contains this text")
    s.add_argument("--page", type=int, help="page number (see next_page)")
    s.add_argument("--limit", type=int, default=50, help="links per page (1-200, default 50)")
    s.set_defaults(func=cmd_links)

    s = sub.add_parser("views", parents=[common], help="who viewed a share link or a document",
                       description="With --link LINK_ID: every view through that share link (ids: `helprange links`). "
                                   "With DOCUMENT_ID: the document's totals and its latest views.")
    s.add_argument("document_id", type=int, nargs="?", metavar="DOCUMENT_ID")
    s.add_argument("--link", type=int, metavar="LINK_ID", help="views through this share link")
    s.add_argument("--page", type=int, help="page number (with --link)")
    s.add_argument("--limit", type=int, default=20, help="how many views (default 20; up to 200 with --link, 100 without)")
    s.set_defaults(func=cmd_views)

    rooms = sub.add_parser("rooms", parents=[common], help="data rooms")
    rsub = rooms.add_subparsers(dest="rooms_cmd", metavar="ACTION")
    rsub.required = True
    rsub.add_parser("list", parents=[common], help="list data rooms")
    r = rsub.add_parser("create", parents=[common], help="create a data room (optionally with folders, an NDA, guests)")
    r.add_argument("name", metavar="NAME")
    r.add_argument("--folder", dest="folders", action="append", metavar="NAME", help="room folder; repeat for several")
    r.add_argument("--nda", action="store_true", help="guests accept an NDA first (HelpRange's investor template)")
    r.add_argument("--nda-id", type=int, metavar="NDA_ID", help="use one of your NDAs (ids: API GET /api/v2/ndas)")
    r.add_argument("--expires", metavar="YYYY-MM-DD", help="last day guests have access")
    r.add_argument("--download", action="store_true", help="allow download and print (default: view only)")
    r.add_argument("--invite", action="append", metavar="EMAIL", help="invite a guest; repeat for several")
    r.add_argument("--no-email", action="store_true", help="add the --invite guests without the invitation e-mail")
    r = rsub.add_parser("delete", parents=[common], help="delete a data room (needs --yes)")
    r.add_argument("room_id", type=int, metavar="ROOM_ID")
    r.add_argument("--yes", action="store_true", help="confirm the deletion")
    for name, helptext in (("show", "guests and documents of a room"), ("index", "the room's numbered index"),
                           ("documents", "documents in a room"), ("guests", "guests of a room and their links")):
        r = rsub.add_parser(name, parents=[common], help=helptext)
        r.add_argument("room_id", type=int, metavar="ROOM_ID")
    r = rsub.add_parser("add", parents=[common], help="add documents to a room")
    r.add_argument("room_id", type=int, metavar="ROOM_ID")
    r.add_argument("document_ids", type=int, nargs="+", metavar="DOCUMENT_ID")
    r.add_argument("--folder", type=int, metavar="ROOM_FOLDER_ID")
    r = rsub.add_parser("invite", parents=[common], help="invite guests (HelpRange e-mails the invitation)")
    r.add_argument("room_id", type=int, metavar="ROOM_ID")
    r.add_argument("emails", nargs="+", metavar="EMAIL")
    r = rsub.add_parser("questions", parents=[common], help="Q&A questions of a room")
    r.add_argument("room_id", type=int, metavar="ROOM_ID")
    r.add_argument("--status", choices=["all", "open", "published", "new", "assigned", "answered", "approved", "declined"])
    rooms.set_defaults(func=cmd_rooms)
    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    for name, default in (("json", False), ("api_key", None), ("base_url", None)):
        if not hasattr(args, name):
            setattr(args, name, default)
    try:
        return args.func(args)
    except CLIError as exc:
        print(f"helprange: {exc}", file=sys.stderr)
        return 2
    except HelpRangeError as exc:
        if args.json:
            json.dump({"error": exc.message, "status": exc.status, "code": exc.code}, sys.stderr)
            sys.stderr.write("\n")
        else:
            print(f"helprange: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
