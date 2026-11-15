# HelpRange Python SDK

Official Python client and CLI for the [HelpRange API](https://www.helprange.com/developers): upload documents, create
tracked share links, see who viewed what (page by page, link by link), create and run data rooms (folders, NDA,
guests, Q&A, request lists), send documents for e-signature, create offers and manage your webhook endpoint.

- Sync (`HelpRange`) and asyncio (`AsyncHelpRange`) clients with the same methods
- Typed responses (`TypedDict`s generated from the [OpenAPI spec](https://www.helprange.com/developers/openapi.json) –
  plain dicts at runtime, full completion in your editor and mypy/pyright checks)
- Automatic `Idempotency-Key` on every POST / PATCH, so retries on 429 / 5xx / network errors are safe for writes too
- Typed exceptions, test-mode detection
- Webhook signature verification
- A `helprange` command-line tool with `--json` output for scripts and agents

Python 3.9+. One dependency: [httpx](https://www.python-httpx.org/).

## Install

```sh
pip install helprange
```

## Quickstart

```python
from helprange import HelpRange

hr = HelpRange()  # reads HELPRANGE_API_KEY; or HelpRange("hr_live_…")

# Upload a PDF and create a tracked share link in one call
result = hr.share("proposal.pdf", label="ACME - Anna", expires_on="2026-12-31", allow_download=False, watermark=True)
print(result["link"]["url"])  # https://www.helprange.com/view/…/proposal.pdf

# Who opened it, when and for how long
stats = hr.documents.get(result["document"]["id"], recent_views=20)
for view in stats["recent_views"]:
    print(view["viewer"], view["opened_at"], view["seconds_read"])
```

Async:

```python
import asyncio
from helprange import AsyncHelpRange

async def main():
    async with AsyncHelpRange() as hr:
        rooms = await hr.data_rooms.list()
        print([r["name"] for r in rooms["data_rooms"]])

asyncio.run(main())
```

## Authentication

Create a team API key in HelpRange → **Settings → API keys**. It acts as the administrator who created it, limited to
its **scopes** (`documents:read`, `documents:write`, `links:read`, `links:write`, `rooms:read`, `rooms:write`,
`analytics:read`, `team:read`). Every method's docstring names the scope it needs.

The key is taken from the `api_key` argument, else `HELPRANGE_API_KEY`. The SDK sends `Authorization: Bearer <key>`.
The REST API is part of the Max and Unlimited plans, the Deal Room Pass and the trial; other plans get
`PaymentRequiredError` (402).

## Sandbox (test mode)

Keys starting with `hr_test_` work on a separate sandbox of your team with sample data – never on live data:

- no e-mail is sent (only addresses at reserved test domains such as `example.com` are accepted; others raise
  `BadRequestError` with `code == "sandbox_email_domain"`), nothing reaches Stripe, sandbox activity sends no webhooks;
- every JSON response carries `"livemode": False`;
- sandbox data is deleted 30 days after the sandbox was created or reset (Settings → API keys → Reset sandbox).

```python
hr = HelpRange("hr_test_…")
hr.test_mode               # True
hr.account.me()["livemode"]  # False
```

## Resources

| Attribute | What |
| --- | --- |
| `hr.account` | Who is connected, the plan and its limits |
| `hr.folders` | Folders and subfolders |
| `hr.documents` | Uploads, documents, statistics and share links |
| `hr.links` | Every share link of the team (filters, pagination) and the views of one link |
| `hr.triggers` | Newest views and uploads (polling) |
| `hr.data_rooms` | Create, change and delete data rooms; the index. Sub-resources: `.guests`, `.documents`, `.folders`, `.questions`, `.request_items`, `.access_requests`, `.signature_requests` |
| `hr.ndas` | The team's NDAs (for a data room's `nda_id`) and whether the plan has NDAs |
| `hr.signature_requests` | E-signature requests and signed PDFs |
| `hr.offers` | Offers with their own link |
| `hr.store` | Store sales and buyer access |
| `hr.lead_forms` | Lead-magnet / landing-page templates |
| `hr.activity` | The team activity feed |
| `hr.webhook_endpoints` | The team's webhook endpoint: create, change, delete, rotate the secret, test, delivery log, redeliver |

Path parameters are positional, everything else is a keyword argument named as in the API reference:
`hr.documents.create_link(250, label="ACME", passcode="oak-41")`. Arguments you leave out are not sent. For the few
fields where `null` means something (e.g. `subfolder_id=None` takes documents out of their subfolder), pass `None`
explicitly. Every method also takes `request_options={"timeout": …, "max_retries": …, "headers": {…}}`; every
POST / PATCH method also takes `idempotency_key=` (see [Retries](#retries-and-limits)).

Uploads accept a path, `bytes` or a binary file object: `hr.documents.upload(file="deck.pdf", folder_id=31)`, or a
public URL: `hr.documents.upload(file_url="https://example.com/deck.pdf")`.

Types live in `helprange.types` (`from helprange.types import ShareLink, GetDocumentResponse`). For an endpoint this
version does not wrap yet: `hr.request("GET", "/api/v2/…")`.

### All endpoints

<!-- BEGIN GENERATED ENDPOINTS -->
| Method | Endpoint | Scope |
| --- | --- | --- |
| `hr.account.me()` | `GET /api/v2/me` | `team:read` |
| `hr.account.plan()` | `GET /api/v2/plan` | `team:read` |
| `hr.folders.list()` | `GET /api/v2/folders` | `documents:read` |
| `hr.folders.get(folder_id)` | `GET /api/v2/folders/{folder_id}` | `documents:read` |
| `hr.folders.set_subfolders_enabled(folder_id, ...)` | `POST /api/v2/folders/{folder_id}` | `documents:write` |
| `hr.folders.list_subfolders(folder_id)` | `GET /api/v2/folders/{folder_id}/subfolders` | `documents:read` |
| `hr.folders.create_subfolder(folder_id, ...)` | `POST /api/v2/folders/{folder_id}/subfolders` | `documents:write` |
| `hr.folders.move_documents(folder_id, ...)` | `POST /api/v2/folders/{folder_id}/subfolders/move` | `documents:write` |
| `hr.folders.rename_subfolder(subfolder_id, ...)` | `POST /api/v2/subfolders/{subfolder_id}` | `documents:write` |
| `hr.folders.delete_subfolder(subfolder_id)` | `POST /api/v2/subfolders/{subfolder_id}/delete` | `documents:write` |
| `hr.documents.list(...)` | `GET /api/v2/documents` | `documents:read` |
| `hr.documents.upload(...)` | `POST /api/v2/files` | `documents:write` |
| `hr.documents.create_link(file_id, ...)` | `POST /api/v2/files/{file_id}/links` | `links:write` |
| `hr.documents.get(file_id, ...)` | `GET /api/v2/documents/{file_id}` | `documents:read` |
| `hr.documents.list_links(file_id)` | `GET /api/v2/documents/{file_id}/links` | `links:read` |
| `hr.links.list(...)` | `GET /api/v2/links` | `links:read` |
| `hr.links.views(link_id, ...)` | `GET /api/v2/links/{link_id}/views` | `analytics:read` |
| `hr.triggers.recent_views()` | `GET /api/v2/views` | `analytics:read` |
| `hr.triggers.recent_uploads()` | `GET /api/v2/uploads` | `documents:read` |
| `hr.store.grant_buyer_access(folder_id, ...)` | `POST /api/v2/folders/{folder_id}/buyers` | `links:write` |
| `hr.store.revoke_buyer_access(folder_id, ...)` | `POST /api/v2/folders/{folder_id}/buyers/remove` | `links:write` |
| `hr.store.list_sales(...)` | `GET /api/v2/store/sales` | `analytics:read` |
| `hr.lead_forms.list_templates()` | `GET /api/v2/landing-templates` | `links:read` |
| `hr.activity.list(...)` | `GET /api/v2/activity` | `analytics:read` |
| `hr.signature_requests.list(...)` | `GET /api/v2/signature-requests` | `documents:read` |
| `hr.signature_requests.create(...)` | `POST /api/v2/signature-requests` | `documents:write` |
| `hr.signature_requests.get(envelope_id)` | `GET /api/v2/signature-requests/{envelope_id}` | `documents:read` |
| `hr.signature_requests.remind(envelope_id)` | `POST /api/v2/signature-requests/{envelope_id}/remind` | `documents:write` |
| `hr.signature_requests.void(envelope_id, ...)` | `POST /api/v2/signature-requests/{envelope_id}/void` | `documents:write` |
| `hr.signature_requests.get_signed_pdf(envelope_id)` | `GET /api/v2/signature-requests/{envelope_id}/signed-pdf` | `documents:read` |
| `hr.data_rooms.list()` | `GET /api/v2/data-rooms` | `rooms:read` |
| `hr.data_rooms.create(...)` | `POST /api/v2/data-rooms` | `rooms:write` |
| `hr.data_rooms.get(data_room_id)` | `GET /api/v2/data-rooms/{data_room_id}` | `rooms:read` |
| `hr.data_rooms.update(data_room_id, ...)` | `POST /api/v2/data-rooms/{data_room_id}` | `rooms:write` |
| `hr.data_rooms.delete(data_room_id, ...)` | `POST /api/v2/data-rooms/{data_room_id}/delete` | `rooms:write` |
| `hr.ndas.list()` | `GET /api/v2/ndas` | `rooms:read` |
| `hr.data_rooms.get_index(data_room_id)` | `GET /api/v2/data-rooms/{data_room_id}/index` | `rooms:read` |
| `hr.data_rooms.guests.list(data_room_id)` | `GET /api/v2/data-rooms/{data_room_id}/guests` | `rooms:read` |
| `hr.data_rooms.guests.invite(data_room_id, ...)` | `POST /api/v2/data-rooms/{data_room_id}/guests` | `rooms:write` |
| `hr.data_rooms.guests.remove(data_room_id, ...)` | `POST /api/v2/data-rooms/{data_room_id}/guests/remove` | `rooms:write` |
| `hr.data_rooms.access_requests.list(data_room_id, ...)` | `GET /api/v2/data-rooms/{data_room_id}/access-requests` | `rooms:read` |
| `hr.data_rooms.signature_requests.list(data_room_id)` | `GET /api/v2/data-rooms/{data_room_id}/signature-requests` | `rooms:read` |
| `hr.data_rooms.questions.list(data_room_id, ...)` | `GET /api/v2/data-rooms/{data_room_id}/questions` | `rooms:read` |
| `hr.data_rooms.questions.add(data_room_id, ...)` | `POST /api/v2/data-rooms/{data_room_id}/questions` | `rooms:write` |
| `hr.data_rooms.request_items.list(data_room_id, ...)` | `GET /api/v2/data-rooms/{data_room_id}/requests` | `rooms:read` |
| `hr.data_rooms.request_items.add(data_room_id, ...)` | `POST /api/v2/data-rooms/{data_room_id}/requests` | `rooms:write` |
| `hr.data_rooms.folders.list(data_room_id)` | `GET /api/v2/data-rooms/{data_room_id}/folders` | `rooms:read` |
| `hr.data_rooms.folders.create(data_room_id, ...)` | `POST /api/v2/data-rooms/{data_room_id}/folders` | `rooms:write` |
| `hr.data_rooms.documents.move(data_room_id, ...)` | `POST /api/v2/data-rooms/{data_room_id}/folders/move` | `rooms:write` |
| `hr.data_rooms.folders.rename(data_room_id, folder_id, ...)` | `POST /api/v2/data-rooms/{data_room_id}/folders/{folder_id}` | `rooms:write` |
| `hr.data_rooms.folders.delete(data_room_id, folder_id)` | `POST /api/v2/data-rooms/{data_room_id}/folders/{folder_id}/delete` | `rooms:write` |
| `hr.data_rooms.documents.list(data_room_id)` | `GET /api/v2/data-rooms/{data_room_id}/documents` | `rooms:read` |
| `hr.data_rooms.documents.add(data_room_id, ...)` | `POST /api/v2/data-rooms/{data_room_id}/documents` | `rooms:write` |
| `hr.data_rooms.documents.remove(data_room_id, ...)` | `POST /api/v2/data-rooms/{data_room_id}/documents/remove` | `rooms:write` |
| `hr.offers.list(...)` | `GET /api/v2/offers` | `links:read` |
| `hr.offers.create(...)` | `POST /api/v2/offers` | `links:write` |
| `hr.offers.get(offer_id)` | `GET /api/v2/offers/{offer_id}` | `links:read` |
| `hr.offers.update(offer_id, ...)` | `PATCH /api/v2/offers/{offer_id}` | `links:write` |
| `hr.offers.add_files(offer_id, ...)` | `POST /api/v2/offers/{offer_id}/files` | `links:write` |
| `hr.offers.remove_files(offer_id, ...)` | `POST /api/v2/offers/{offer_id}/files/remove` | `links:write` |
| `hr.offers.list_responses(offer_id, ...)` | `GET /api/v2/offers/{offer_id}/responses` | `analytics:read` |
| `hr.offers.list_all_responses(...)` | `GET /api/v2/offer-responses` | `analytics:read` |
| `hr.webhook_endpoints.list()` | `GET /api/v2/webhook-endpoints` | `webhooks:manage` |
| `hr.webhook_endpoints.create(...)` | `POST /api/v2/webhook-endpoints` | `webhooks:manage` |
| `hr.webhook_endpoints.get(endpoint_id)` | `GET /api/v2/webhook-endpoints/{endpoint_id}` | `webhooks:manage` |
| `hr.webhook_endpoints.update(endpoint_id, ...)` | `POST /api/v2/webhook-endpoints/{endpoint_id}` | `webhooks:manage` |
| `hr.webhook_endpoints.delete(endpoint_id)` | `POST /api/v2/webhook-endpoints/{endpoint_id}/delete` | `webhooks:manage` |
| `hr.webhook_endpoints.rotate_secret(endpoint_id)` | `POST /api/v2/webhook-endpoints/{endpoint_id}/rotate-secret` | `webhooks:manage` |
| `hr.webhook_endpoints.send_test(endpoint_id)` | `POST /api/v2/webhook-endpoints/{endpoint_id}/test` | `webhooks:manage` |
| `hr.webhook_endpoints.deliveries(endpoint_id, ...)` | `GET /api/v2/webhook-endpoints/{endpoint_id}/deliveries` | `webhooks:manage` |
| `hr.webhook_endpoints.redeliver(endpoint_id, delivery_id)` | `POST /api/v2/webhook-endpoints/{endpoint_id}/deliveries/{delivery_id}/redeliver` | `webhooks:manage` |
<!-- END GENERATED ENDPOINTS -->

## Data rooms

```python
# NDAs need the Max plan (or the Deal Room Pass / trial)
nda_available = hr.ndas.list()["nda_available"]

room = hr.data_rooms.create(
    name="Project Falcon",
    folders=["1. Corporate", "2. Financials", "3. Legal"],
    settings={"download": False, "watermark": True, "nda": nda_available, "nda_template": "investor", "nda_mode": "click"},
)
print(room["links"]["guest_link"])  # the room's shareable link

hr.data_rooms.documents.add(room["id"], document_ids=[250, 251], folder_id=room["folders"][1]["id"])

guest = hr.data_rooms.guests.invite(room["id"], email="jane@example.com")
print(guest["link"])  # Jane's own link – also e-mailed to her unless send_invite=False

hr.data_rooms.guests.list(room["id"])
hr.data_rooms.guests.remove(room["id"], email="jane@example.com")
hr.data_rooms.update(room["id"], settings={"expires_on": "2026-12-31"})

# Deleting a room (and its guest access) needs an explicit confirmation
hr.data_rooms.delete(room["id"], confirm=True)
```

## Links and views

```python
# Every share link of the team – filter by document_id, folder_id, room_id, label, status, created_after/_before
page = 1
while page:
    res = hr.links.list(document_id=250, status="active", page=page, limit=200)
    for link in res["links"]:
        print(link["id"], link["label"], link["views"], link["url"])
    page = res["next_page"]

# Who opened one link, when, for how long
for v in hr.links.views(264, limit=100)["views"]:
    print(v["viewer"], v["opened_at"], v["seconds_read"], v["pages_read"])
```

## Errors

Every exception is a `helprange.HelpRangeError` with `status`, `code` (the API's machine-readable reason, when it
sends one), `message` and the parsed `body`:

| Exception | When |
| --- | --- |
| `BadRequestError` | 400 – e.g. a duplicate link label, `sandbox_email_domain` |
| `AuthenticationError` | 401 – `invalid_key`, `key_revoked`, `key_expired`, `key_owner_removed` |
| `PaymentRequiredError` | 402 – the plan does not include the API / feature |
| `PermissionDeniedError` | 403 – `insufficient_scope` (see `.required_scope`) |
| `NotFoundError` | 404 |
| `ConflictError` | 409 – e.g. a frozen room, the team already has a webhook endpoint |
| `IdempotencyKeyInProgressError` | 409 `idempotency_key_in_progress` (a `ConflictError`) – still running after the in-progress retries |
| `UnprocessableEntityError` | 422 |
| `IdempotencyKeyReusedError` | 422 `idempotency_key_reused` (an `UnprocessableEntityError`) – the key was used for a different request |
| `PayloadTooLargeError` | 413 – `FILE_TOO_LARGE`, `REQUEST_TOO_LARGE` |
| `LockedError` | 423 – e.g. `ROOM_FROZEN` |
| `RateLimitError` | 429 – `RATE_LIMITED`, `DAILY_LIMIT`, `PAUSED`, `UPLOAD_LIMIT` (see `.retry_after`) |
| `InternalServerError` | 5xx |
| `APIConnectionError` / `APITimeoutError` | no HTTP answer / timed out |
| `WebhookVerificationError` | `verify_webhook()` rejected a delivery |

```python
from helprange import PermissionDeniedError, RateLimitError

try:
    hr.data_rooms.guests.invite(10, email="jane@example.com")
except PermissionDeniedError as e:
    print("missing scope:", e.required_scope)
except RateLimitError as e:
    print(f"over a limit ({e.code}); retry in {e.retry_after}s")
```

## Retries and limits

Every `POST` and `PATCH` carries an `Idempotency-Key` header – a new UUID v4 per call, **the same one for every retry
of that call**. The API runs a keyed request once and answers a repeat with the stored response (header
`Idempotent-Replayed: true`), so a retried write never creates a second data room, share link or invitation.

- **429** (any method) – the API did not carry out the request. The client waits `Retry-After` and retries, unless the
  wait is longer than `max_retry_after` (default 60 s – e.g. a daily cap or a paused API); then it raises
  `RateLimitError` at once.
- **408 / 5xx, connection errors and timeouts** – retried for `GET` and for keyed `POST` / `PATCH`, with exponential
  backoff (0.5 s, 1 s, 2 s … up to 8 s, with jitter; a short `Retry-After` is respected).
- **409 `idempotency_key_in_progress`** – the first attempt is still running on the server (typically after a
  timeout). The client waits with backoff (~1, 2, 4, 8, 8 s) and asks again, up to 5 times, without using up
  `max_retries`; then it raises `IdempotencyKeyInProgressError`.
- **422 `idempotency_key_reused`** – never retried; raises `IdempotencyKeyReusedError`. It means the key was used in the
  last 24 hours for a different method, path or body.

Pass your own key to make a write safe to repeat across processes or restarts (e.g. a job id):

```python
hr.data_rooms.create(name="Project Falcon", idempotency_key=f"deal-{deal.id}-room")
# or, on any method: request_options={"idempotency_key": "…"}
```

Keys are kept for 24 hours, per API key. `hr.share(..., request_options={"idempotency_key": k})` uses `k` for the
upload and `k:link` for the share link.

`max_retries` (default 2) and `timeout` (default 60 s per attempt) can be set on the client or per request.
After each response `hr.rate_limit` holds `limit`, `remaining`, `reset` and `livemode` from the response headers.
Team limits: 3,600 requests an hour, 120 a minute, 300 writes an hour, 2,000 share links and 1,000 guests a day.

## Webhooks

HelpRange POSTs signed JSON events (`document.opened`, `file_request.uploaded`, `room.access_requested`,
`nda.accepted`, `document.acknowledged`, `offer.accepted`, `offer.declined`, `offer.contact_requested`) to the endpoint
you set in Settings → Integrations or through `hr.webhook_endpoints`. Verify each delivery with the **raw** body:

```python
# Flask
import os

from flask import Flask, request
from helprange import verify_webhook, WebhookVerificationError

app = Flask(__name__)

@app.post("/webhooks/helprange")
def helprange_webhook():
    try:
        event = verify_webhook(request.get_data(), request.headers, os.environ["HELPRANGE_WEBHOOK_SECRET"])
    except WebhookVerificationError:
        return "", 400
    # deduplicate on event["id"] – retries carry the same id
    if event["event"] == "document.opened":
        print(event["data"])
    return "", 200  # answer 2xx within 10 seconds
```

Django: `verify_webhook(request.body, request.headers, secret)`; FastAPI: `verify_webhook(await request.body(),
request.headers, secret)`.

The scheme: `HelpRange-Signature: t=<unix>,v1=<hex HMAC-SHA256(secret, "<t>.<raw body>")>`. `verify_webhook` accepts
a timestamp within 5 minutes (`tolerance=` to change it) and any `v1` that matches – during the 24 hours after a secret
rotation HelpRange sends two. Pass a list of secrets if you rotate on your side. `sign_webhook_payload()` builds a valid
header for your tests. See the [webhooks guide](https://www.helprange.com/developers/webhooks).

Manage the endpoint from code:

```python
ep = hr.webhook_endpoints.create(url="https://example.com/webhooks/helprange")
print(ep["secret"])                                    # shown once – store it
hr.webhook_endpoints.send_test(ep["id"])               # a test event, delivered right away
failed = hr.webhook_endpoints.deliveries(ep["id"], status="failed")["deliveries"]
if failed:
    hr.webhook_endpoints.redeliver(ep["id"], failed[0]["id"])
secret = hr.webhook_endpoints.rotate_secret(ep["id"])["secret"]  # the old secret keeps signing for 24 hours
hr.webhook_endpoints.update(ep["id"], enabled=True)    # turn it back on after 410 Gone / repeated failures
hr.webhook_endpoints.delete(ep["id"])
```

## Command line

```sh
helprange login                                  # prompts for the key, checks it, saves ~/.config/helprange/config (0600)
helprange whoami
helprange share proposal.pdf --to anna@acme.com --to bob@acme.com --expires 2026-12-31 --no-download --watermark
helprange share https://example.com/deck.pdf     # a public URL works too
helprange documents
helprange links                                  # every active share link of the team
helprange links --document 250 --status all      # filters: --document --folder --room --status --label (+ --page --limit)
helprange views --link 264                       # who opened link 264, when, how long
helprange views 250                              # a document's totals and latest views
helprange rooms create "Project Falcon" --folder Corporate --folder Financials --nda \
    --invite jane@example.com --invite max@example.com   # prints the guest link and each guest's own link
helprange rooms list
helprange rooms show 10 | index 10 | documents 10 | guests 10 | questions 10 --status open
helprange rooms add 10 250 251                   # add documents 250 and 251 to room 10
helprange rooms invite 10 jane@example.com       # HelpRange e-mails the invitation
helprange rooms delete 10 --yes                  # without --yes nothing is deleted
```

- `--json` on any command prints JSON (errors go to stderr as JSON too) – meant for scripts and AI agents.
- The key: `--api-key`, else `HELPRANGE_API_KEY`, else the saved one. `helprange logout` forgets it.
- `share --to` creates **one link per recipient**, labelled with their e-mail, so the statistics show who opened what.
  HelpRange does not e-mail links created through the API – send them yourself.
- Exit codes: 0 ok, 1 API error, 2 usage / configuration error.

`python -m helprange …` works the same.

## Examples

[`examples/`](examples): [`share_pdf.py`](examples/share_pdf.py) (share a PDF and get a link),
[`who_viewed.py`](examples/who_viewed.py) (who viewed a document, through which link, time per page),
[`data_room.py`](examples/data_room.py) (async: create a room with folders and an NDA, add documents, invite guests
and print their links, index, Q&A),
[`webhook_endpoints.py`](examples/webhook_endpoints.py) (create / update the endpoint, test event, redeliver, rotate
the secret),
[`webhook_server.py`](examples/webhook_server.py) (stdlib webhook receiver).

## Why httpx

httpx is the one dependency: it gives the sync and the async client the same request model, real connect/read
timeouts, connection pooling, correct multipart uploads and `MockTransport` for tests, and is already installed in
most modern Python stacks (it is pure Python). The stdlib (`urllib`) has no async client, so an async SDK on top of it
would need threads, and it lacks pooling and multipart.

## Development

```sh
python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'
.venv/bin/pytest -q          # fake transport, no network
.venv/bin/ruff check src tests examples && .venv/bin/mypy src examples
```

`src/helprange/_generated/` is generated from the OpenAPI spec – don't edit it by hand; see the generator in the
`helprange-sdks` workspace.

## License

MIT © HelpRange
