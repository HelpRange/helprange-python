import asyncio
import os

import httpx
import pytest

import helprange
from helprange import (
    NOT_GIVEN,
    APIConnectionError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    HelpRangeError,
    InternalServerError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
)

from .conftest import KEY


def test_get_sends_key_query_and_parses(client, rec):
    rec.add(body={"documents": [{"id": 250, "name": "proposal.pdf"}], "livemode": True})
    res = client.documents.list(folder_id=31, subfolder="none")
    assert res["documents"][0]["id"] == 250
    r = rec.requests[0]
    assert r.method == "GET"
    assert r.url.path == "/api/v2/documents"
    assert dict(r.url.params) == {"folder_id": "31", "subfolder": "none"}
    assert r.headers["authorization"] == f"Bearer {KEY}"
    assert r.headers["user-agent"].startswith("helprange-python/")
    assert r.content == b""


def test_post_json_body_drops_unset_and_keeps_explicit_null(client, rec):
    rec.add(201, {"id": 264, "url": "https://www.helprange.com/view/x/p.pdf"})
    client.documents.create_link(250, label="ACME - Anna", expires_on="2026-12-31", watermark=True)
    assert str(rec.requests[0].url) == "https://www.helprange.com/api/v2/files/250/links"
    assert rec.json() == {"label": "ACME - Anna", "expires_on": "2026-12-31", "watermark": True}

    rec.add(201, {}).add(200, {})
    client.documents.create_link(250, views_limit=None)
    assert rec.json() == {"views_limit": None}
    client.folders.move_documents(31, document_ids=[1, 2], subfolder_id=None)
    assert rec.json() == {"document_ids": [1, 2], "subfolder_id": None}
    assert NOT_GIVEN is helprange.NotGiven()


def test_path_params_are_encoded(client, rec):
    rec.add(body={})
    client.signature_requests.get("a/b c")
    assert rec.requests[0].url.raw_path == b"/api/v2/signature-requests/a%2Fb%20c"


def test_every_tag_is_a_resource(client):
    for name in ("account", "folders", "documents", "links", "triggers", "data_rooms", "ndas", "signature_requests",
                 "offers", "store", "lead_forms", "activity", "webhook_endpoints"):
        assert hasattr(client, name), name
    assert callable(client.data_rooms.guests.invite)


def test_test_mode_and_env_key(monkeypatch):
    assert helprange.HelpRange(KEY).test_mode is False
    assert helprange.HelpRange("hr_test_abc").test_mode is True
    monkeypatch.delenv("HELPRANGE_API_KEY", raising=False)
    with pytest.raises(HelpRangeError):
        helprange.HelpRange()
    monkeypatch.setenv("HELPRANGE_API_KEY", "hr_test_env")
    assert helprange.HelpRange().test_mode is True
    assert KEY not in repr(helprange.HelpRange(KEY))


def test_typed_errors(client, rec):
    client.max_retries = 0
    rec.add(403, {"error": 'no "rooms:write" scope', "code": "insufficient_scope", "required_scope": "rooms:write"})
    rec.add(401, {"error": "Unknown key.", "code": "invalid_key"})
    rec.add(404, {"error": "Not found."})
    rec.add(400, {"error": "Reserved test domains only.", "code": "sandbox_email_domain"})
    rec.add(404, {"status": "Not Found Error", "message": "Directory not found"})
    with pytest.raises(PermissionDeniedError) as e:
        client.data_rooms.guests.invite(10, email="a@b.com")
    assert (e.value.status, e.value.code, e.value.required_scope) == (403, "insufficient_scope", "rooms:write")
    assert isinstance(e.value, HelpRangeError)
    with pytest.raises(AuthenticationError) as e2:
        client.account.me()
    assert e2.value.code == "invalid_key"
    with pytest.raises(NotFoundError):
        client.documents.get(1)
    with pytest.raises(BadRequestError) as e4:
        client.data_rooms.guests.invite(10, email="a@b.com")
    assert e4.value.code == "sandbox_email_domain"
    with pytest.raises(NotFoundError) as e5:
        client.request("get", "/public-api/directory/1/file")
    assert e5.value.message == "Directory not found"


def test_429_retried_for_post(client, rec):
    rec.add(429, {"error": "Slow down", "code": "RATE_LIMITED", "retry_after": 1}, {"retry-after": "1"})
    rec.add(201, {"id": 1})
    assert client.documents.create_link(1)["id"] == 1
    assert len(rec.requests) == 2


def test_long_retry_after_is_raised(client, rec):
    rec.add(429, {"error": "Daily cap", "code": "DAILY_LIMIT", "retry_after": 3600}, {"retry-after": "3600"})
    with pytest.raises(RateLimitError) as e:
        client.documents.list()
    assert e.value.retry_after == 3600 and e.value.code == "DAILY_LIMIT"
    assert len(rec.requests) == 1


def test_5xx_retried_for_get(client, rec):
    rec.add(503, "down", {"content-type": "text/plain"}).add(200, {"ok": True})
    assert client.account.plan() == {"ok": True}
    assert len(rec.requests) == 2
    assert "idempotency-key" not in rec.requests[0].headers  # GET never carries a key


def test_max_retries(client, rec):
    for _ in range(3):
        rec.add(500, {"error": "boom"})
    with pytest.raises(InternalServerError):
        client.folders.list()
    assert len(rec.requests) == 3


def test_connection_and_timeout_errors(client, rec):
    rec.fail(httpx.ConnectError("refused")).add(200, {"folders": []})
    assert client.folders.list() == {"folders": []}
    client.max_retries = 0
    rec.fail(httpx.ReadTimeout("slow"))
    with pytest.raises(APITimeoutError):
        client.account.me()
    rec.fail(httpx.ConnectError("refused"))
    with pytest.raises(APIConnectionError):
        client.documents.upload(file_url="https://example.com/a.pdf")


def test_upload_multipart_from_path_and_bytes(client, rec, tmp_path):
    f = tmp_path / "deck.pdf"
    f.write_bytes(b"%PDF-1.4 test")
    rec.add(201, {"id": 250}).add(201, {"id": 251})
    client.documents.upload(file=f, folder_id=31)
    r = rec.requests[0]
    assert r.headers["content-type"].startswith("multipart/form-data")
    assert b'name="file"; filename="deck.pdf"' in r.content
    assert b"%PDF-1.4 test" in r.content
    assert b'name="folder_id"' in r.content
    client.documents.upload(file=b"abc", filename="x.pdf")
    assert b'filename="x.pdf"' in rec.requests[1].content


def test_upload_by_url_is_json(client, rec):
    rec.add(201, {"id": 1})
    client.documents.upload(file_url="https://example.com/proposal.pdf", folder_id=31)
    assert rec.json() == {"file_url": "https://example.com/proposal.pdf", "folder_id": 31}


def test_share(client, rec):
    rec.add(201, {"id": 250, "name": "deck.pdf"}).add(201, {"id": 264, "url": "https://www.helprange.com/view/abc/deck.pdf"})
    res = client.share(b"%PDF", filename="deck.pdf", label="ACME", allow_download=False)
    assert res["link"]["url"].endswith("deck.pdf")
    assert rec.requests[1].url.path == "/api/v2/files/250/links"
    assert rec.json() == {"label": "ACME", "allow_download": False}


def test_rate_limit_headers(rec):
    c = helprange.HelpRange("hr_test_x", http_client=httpx.Client(transport=httpx.MockTransport(rec)))
    rec.add(200, {}, {"x-ratelimit-limit": "3600", "x-ratelimit-remaining": "3599", "x-ratelimit-reset": "1763200800",
                      "x-helprange-livemode": "false"})
    c.account.me()
    assert c.rate_limit == {"limit": 3600, "remaining": 3599, "reset": 1763200800, "livemode": False}


def test_parse_retry_after():
    assert helprange.parse_retry_after("7") == 7
    assert helprange.parse_retry_after("Thu, 01 Jan 1970 00:00:10 GMT", now=0) == 10
    assert helprange.parse_retry_after("soon") is None


def test_async_client(aclient, rec):
    rec.add(429, {"error": "x", "code": "RATE_LIMITED", "retry_after": 1}, {"retry-after": "0"})
    rec.add(200, {"data_rooms": [{"id": 10, "name": "Falcon"}]})
    rec.add(201, {"id": 5, "email": "jane@example.com", "already_a_guest": False})

    async def run():
        async with aclient as hr:
            rooms = await hr.data_rooms.list()
            guest = await hr.data_rooms.guests.invite(rooms["data_rooms"][0]["id"], email="jane@example.com")
            return rooms, guest

    rooms, guest = asyncio.run(run())
    assert rooms["data_rooms"][0]["name"] == "Falcon"
    assert guest["id"] == 5
    assert rec.json() == {"email": "jane@example.com"}
    assert rec.requests[-1].url.path == "/api/v2/data-rooms/10/guests"


def test_async_errors(aclient, rec):
    rec.add(404, {"error": "No such room."})

    async def run():
        await aclient.data_rooms.get(99)

    with pytest.raises(NotFoundError):
        asyncio.run(run())


def test_types_module():
    from helprange.types import ShareLink, WebhookEventType  # noqa: F401
    assert "ShareLink" in __import__("helprange.types", fromlist=["__all__"]).__all__
    assert os.path.basename(helprange.__file__) == "__init__.py"
