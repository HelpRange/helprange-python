import json
import os
import stat

import httpx
import pytest

import helprange
from helprange import cli


@pytest.fixture
def env(tmp_path, monkeypatch, rec):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    monkeypatch.delenv("HELPRANGE_API_KEY", raising=False)
    monkeypatch.delenv("HELPRANGE_BASE_URL", raising=False)

    def fake(key, base_url=None):
        return helprange.HelpRange(key, base_url=base_url, http_client=httpx.Client(transport=httpx.MockTransport(rec)))

    monkeypatch.setattr(cli, "HelpRange", fake)
    return tmp_path


def run(capsys, *argv):
    code = cli.main(list(argv))
    out = capsys.readouterr()
    return code, out.out, out.err


def test_login_saves_key_0600(env, rec, capsys):
    rec.add(200, {"email": "owner@example.com", "name": "Owner", "team": "ACME", "plan": "Max", "livemode": False})
    code, out, _ = run(capsys, "login", "--key", "hr_test_abc")
    assert code == 0 and "owner@example.com" in out and "test mode" in out
    path = cli.config_path()
    assert json.loads(path.read_text())["api_key"] == "hr_test_abc"
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    assert rec.requests[0].headers["authorization"] == "Bearer hr_test_abc"


def test_login_rejects_bad_key(env, rec, capsys):
    rec.add(401, {"error": "Unknown key.", "code": "invalid_key"})
    code, _, err = run(capsys, "login", "--key", "hr_live_bad")
    assert code == 2 and "refused" in err
    assert not cli.config_path().exists()


def test_no_key(env, capsys):
    code, _, err = run(capsys, "documents")
    assert code == 2 and "helprange login" in err


def test_share_one_link_per_recipient(env, rec, capsys, monkeypatch, tmp_path):
    monkeypatch.setenv("HELPRANGE_API_KEY", "hr_test_env")
    f = tmp_path / "deck.pdf"
    f.write_bytes(b"%PDF")
    rec.add(201, {"id": 250, "name": "deck.pdf"})
    rec.add(201, {"id": 1, "label": "anna@example.com", "url": "https://www.helprange.com/view/a/deck.pdf"})
    rec.add(201, {"id": 2, "label": "bob@example.com", "url": "https://www.helprange.com/view/b/deck.pdf"})
    code, out, _ = run(capsys, "share", str(f), "--to", "anna@example.com", "--to", "bob@example.com",
                       "--expires", "2026-12-31", "--no-download", "--watermark", "--json")
    assert code == 0
    data = json.loads(out)
    assert [link["url"] for link in data["links"]] == ["https://www.helprange.com/view/a/deck.pdf",
                                                 "https://www.helprange.com/view/b/deck.pdf"]
    assert b'filename="deck.pdf"' in rec.requests[0].content
    assert rec.json(1) == {"label": "anna@example.com", "expires_on": "2026-12-31", "allow_download": False, "watermark": True}


def test_share_url_prints_link(env, rec, capsys):
    rec.add(201, {"id": 250, "name": "p.pdf"}).add(201, {"id": 1, "label": "x", "url": "https://www.helprange.com/view/z/p.pdf"})
    code, out, _ = run(capsys, "--api-key", "hr_live_k", "share", "https://example.com/p.pdf")
    assert code == 0 and out.strip().endswith("https://www.helprange.com/view/z/p.pdf")
    assert json.loads(rec.requests[0].content) == {"file_url": "https://example.com/p.pdf"}


LINK = {"id": 264, "document": "deck.pdf", "label": "ACME", "status": "active", "views": 2, "expires_on": None,
        "url": "https://www.helprange.com/view/a/deck.pdf"}


def test_links_lists_all_with_filters(env, rec, capsys, monkeypatch):
    monkeypatch.setenv("HELPRANGE_API_KEY", "hr_live_k")
    rec.add(200, {"links": [LINK], "page": 1, "limit": 50, "total": 1, "next_page": None})
    code, out, _ = run(capsys, "links")
    assert code == 0 and "ACME" in out and "deck.pdf" in out
    assert rec.requests[-1].url.path == "/api/v2/links"
    assert dict(rec.requests[-1].url.params) == {"limit": "50"}

    rec.add(200, {"links": [LINK], "page": 2, "limit": 10, "total": 21, "next_page": 3})
    code, out, err = run(capsys, "links", "--document", "250", "--folder", "31", "--room", "12", "--status", "all",
                         "--label", "AC", "--page", "2", "--limit", "10", "--json")
    assert code == 0 and json.loads(out)["links"][0]["id"] == 264
    assert dict(rec.requests[-1].url.params) == {"document_id": "250", "folder_id": "31", "room_id": "12",
                                                 "status": "all", "label": "AC", "page": "2", "limit": "10"}


def test_views_of_a_link_and_of_a_document(env, rec, capsys, monkeypatch):
    monkeypatch.setenv("HELPRANGE_API_KEY", "hr_live_k")
    rec.add(200, {"link": LINK, "views": [{"id": 1, "opened_at": "2026-11-09T14:02:11+00:00", "viewer": "anna@client.com",
                                           "seconds_read": 30, "pages_read": 4, "country": "DE", "downloaded": False}],
                  "page": 1, "limit": 20, "total": 1, "next_page": None})
    code, out, _ = run(capsys, "views", "--link", "264")
    assert code == 0 and "anna@client.com" in out and "ACME" in out
    assert rec.requests[-1].url.path == "/api/v2/links/264/views"

    rec.add(200, {"link": LINK, "views": [], "page": 1, "limit": 5, "total": 0, "next_page": None})
    code, out, _ = run(capsys, "views", "--link", "264", "--limit", "5", "--json")
    assert json.loads(out)["total"] == 0 and rec.requests[-1].url.params["limit"] == "5"

    rec.add(200, {"name": "deck.pdf", "views": 2, "downloads": 0, "total_seconds_read": 30, "recent_views": [
        {"viewer": "bob@client.com", "opened_at": "t", "seconds_read": 30, "country": "DE", "downloaded": False}]})
    code, out, _ = run(capsys, "views", "250", "--limit", "5")
    assert "bob@client.com" in out
    assert rec.requests[-1].url.params["recent_views"] == "5"

    code, _, err = run(capsys, "views")
    assert code == 2 and "--link" in err


ROOM = {"id": 12, "name": "Falcon", "nda_required": "Investor NDA", "folders": [{"id": 1, "name": "Legal"},
        {"id": 2, "name": "Financials"}], "links": {"guest_link": "https://www.helprange.com/r/abc"}}


def test_rooms_create_with_folders_nda_and_guests(env, rec, capsys, monkeypatch):
    monkeypatch.setenv("HELPRANGE_API_KEY", "hr_live_k")
    rec.add(201, ROOM)
    rec.add(201, {"id": 5, "email": "jane@example.com", "link": "https://www.helprange.com/r/jane", "invited": True,
                  "already_a_guest": False})
    rec.add(201, {"id": 6, "email": "max@example.com", "link": "https://www.helprange.com/r/max", "invited": True,
                  "already_a_guest": False})
    code, out, _ = run(capsys, "rooms", "create", "Falcon", "--folder", "Legal", "--folder", "Financials", "--nda",
                       "--invite", "jane@example.com", "--invite", "max@example.com")
    assert code == 0
    assert "https://www.helprange.com/r/abc" in out and "jane@example.com: https://www.helprange.com/r/jane" in out
    assert rec.json(0) == {"name": "Falcon", "folders": ["Legal", "Financials"], "settings": {"nda": True}}
    assert [r.url.path for r in rec.requests] == ["/api/v2/data-rooms", "/api/v2/data-rooms/12/guests",
                                                  "/api/v2/data-rooms/12/guests"]
    assert rec.json(1) == {"email": "jane@example.com"}
    # each call has its own Idempotency-Key
    assert len({r.headers["idempotency-key"] for r in rec.requests}) == 3

    rec.add(201, {**ROOM, "folders": [], "nda_required": None})
    code, out, _ = run(capsys, "rooms", "create", "Plain", "--nda-id", "7", "--expires", "2026-12-31", "--json")
    assert json.loads(out)["data_room"]["id"] == 12 and json.loads(out)["guests"] == []
    assert rec.json() == {"name": "Plain", "settings": {"nda_id": 7, "expires_on": "2026-12-31"}}


def test_rooms_delete_needs_yes(env, rec, capsys, monkeypatch):
    monkeypatch.setenv("HELPRANGE_API_KEY", "hr_live_k")
    code, _, err = run(capsys, "rooms", "delete", "12")
    assert code == 2 and "--yes" in err and not rec.requests
    rec.add(200, {"deleted": True, "id": 12, "name": "Falcon"})
    code, out, _ = run(capsys, "rooms", "delete", "12", "--yes", "--json")
    assert code == 0 and json.loads(out)["deleted"] is True
    assert rec.requests[-1].url.path == "/api/v2/data-rooms/12/delete" and rec.json() == {"confirm": True}


def test_rooms_list_invite_guests(env, rec, capsys, monkeypatch):
    monkeypatch.setenv("HELPRANGE_API_KEY", "hr_live_k")
    rec.add(200, {"data_rooms": [{"id": 10, "name": "Falcon", "guests": 1, "documents": 2,
                                  "pending_access_requests": 0, "frozen": False}]})
    code, out, _ = run(capsys, "rooms", "list")
    assert "Falcon" in out

    rec.add(201, {"id": 5, "email": "jane@example.com", "data_room_id": 10, "link": "https://www.helprange.com/r/j",
                  "invited": True, "already_a_guest": False})
    code, out, _ = run(capsys, "rooms", "invite", "10", "jane@example.com")
    assert "jane@example.com: invited – https://www.helprange.com/r/j" in out
    assert rec.requests[-1].url.path == "/api/v2/data-rooms/10/guests"

    rec.add(200, {"data_room_id": 10, "guests": [{"id": 5, "email": "jane@example.com", "link": "https://www.helprange.com/r/j"}]})
    code, out, _ = run(capsys, "rooms", "guests", "10")
    assert "https://www.helprange.com/r/j" in out and rec.requests[-1].url.path == "/api/v2/data-rooms/10/guests"


def test_api_errors_exit_1_with_json(env, rec, capsys, monkeypatch):
    monkeypatch.setenv("HELPRANGE_API_KEY", "hr_live_k")
    rec.add(402, {"error": "The REST API is part of the Max plan."})
    code, _, err = run(capsys, "documents", "--json")
    assert code == 1 and json.loads(err)["status"] == 402
