"""Idempotency-Key handling and the retries it makes safe – no network (httpx.MockTransport)."""
import asyncio
import re
import uuid

import httpx
import pytest

import helprange
from helprange import (
    APIConnectionError,
    ConflictError,
    IdempotencyKeyInProgressError,
    IdempotencyKeyReusedError,
    InternalServerError,
    UnprocessableEntityError,
)

UUID4 = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
BUSY = {"error": "A request with this Idempotency-Key is still running.", "code": "idempotency_key_in_progress"}


def keys(rec):
    return [r.headers.get("idempotency-key") for r in rec.requests]


def test_post_and_patch_get_a_fresh_uuid4_get_none(client, rec):
    rec.add(201, {"id": 1}).add(201, {"id": 2}).add(200, {}).add(200, {})
    client.data_rooms.create(name="A")
    client.data_rooms.create(name="B")
    client.offers.update("o1", title="x")
    client.data_rooms.list()
    a, b, patch, get = keys(rec)
    assert UUID4.match(a) and UUID4.match(b) and a != b
    assert rec.requests[2].method == "PATCH" and UUID4.match(patch)
    assert get is None
    assert uuid.UUID(a).version == 4


def test_own_key_via_argument_options_or_header(client, rec):
    rec.add(201, {}).add(201, {}).add(201, {})
    client.data_rooms.guests.invite(10, email="jane@example.com", idempotency_key="invite-10-jane")
    client.data_rooms.guests.invite(10, email="jane@example.com", request_options={"idempotency_key": "opt"})
    client.data_rooms.guests.invite(10, email="jane@example.com", request_options={"headers": {"Idempotency-Key": "hdr"}})
    assert keys(rec) == ["invite-10-jane", "opt", "hdr"]
    assert rec.json(0) == {"email": "jane@example.com"}  # the key is a header, never a body field


def test_post_retried_on_5xx_with_the_same_key(client, rec):
    rec.add(502, {"error": "Bad gateway"}).add(503, "down", {"content-type": "text/plain"})
    rec.add(201, {"id": 42, "name": "Falcon"}, {"idempotent-replayed": "true"})
    assert client.data_rooms.create(name="Falcon")["id"] == 42
    k = keys(rec)
    assert len(k) == 3 and len(set(k)) == 1 and UUID4.match(k[0])
    assert all(r.content == rec.requests[0].content for r in rec.requests)


def test_post_retried_on_connection_errors_and_timeouts(client, rec):
    rec.fail(httpx.ConnectError("reset")).fail(httpx.ReadTimeout("slow")).add(201, {"id": 7})
    assert client.webhook_endpoints.create(url="https://example.com/h")["id"] == 7
    assert len(set(keys(rec))) == 1 and len(rec.requests) == 3


def test_post_gives_up_after_max_retries(client, rec):
    client.max_retries = 1
    rec.add(500, {"error": "boom"}).add(500, {"error": "boom"})
    with pytest.raises(InternalServerError):
        client.documents.create_link(1)
    rec.fail(httpx.ConnectError("a")).fail(httpx.ConnectError("b"))
    with pytest.raises(APIConnectionError):
        client.documents.create_link(1)
    assert len(rec.requests) == 4


def test_409_in_progress_retried_with_backoff(client, rec, monkeypatch):
    waits = []
    monkeypatch.setattr(helprange._client.time, "sleep", waits.append)
    client.max_retries = 1
    rec.fail(httpx.ReadTimeout("slow")).add(409, BUSY).add(409, BUSY).add(201, {"id": 3})
    assert client.data_rooms.create(name="Slow")["id"] == 3
    assert len(rec.requests) == 4 and len(set(keys(rec))) == 1
    # backoff after the timeout, then ~1 s and ~2 s for the in-progress answers (jitter 75-100 %)
    assert 0.75 <= waits[1] <= 1.0 and 1.5 <= waits[2] <= 2.0


def test_409_in_progress_gives_up_with_typed_error(client, rec):
    for _ in range(helprange.IN_PROGRESS_MAX_RETRIES + 1):
        rec.add(409, BUSY, {"retry-after": "0"})
    with pytest.raises(IdempotencyKeyInProgressError) as e:
        client.data_rooms.create(name="Slow")
    assert isinstance(e.value, ConflictError) and e.value.code == "idempotency_key_in_progress"
    assert len(rec.requests) == helprange.IN_PROGRESS_MAX_RETRIES + 1


def test_in_progress_not_retried_with_max_retries_0(client, rec):
    client.max_retries = 0
    rec.add(409, BUSY)
    with pytest.raises(IdempotencyKeyInProgressError):
        client.data_rooms.create(name="Slow")
    assert len(rec.requests) == 1


def test_other_409_not_retried(client, rec):
    rec.add(409, {"error": "The team already has a webhook endpoint."})
    with pytest.raises(ConflictError) as e:
        client.webhook_endpoints.create(url="https://example.com/h")
    assert not isinstance(e.value, IdempotencyKeyInProgressError)
    assert len(rec.requests) == 1


def test_422_reused_is_typed_and_not_retried(client, rec):
    rec.add(422, {"error": "This Idempotency-Key was already used with a different request.", "code": "idempotency_key_reused"})
    with pytest.raises(IdempotencyKeyReusedError) as e:
        client.data_rooms.create(name="X", idempotency_key="k1")
    assert isinstance(e.value, UnprocessableEntityError)
    assert (e.value.status, e.value.code) == (422, "idempotency_key_reused")
    assert len(rec.requests) == 1


def test_multipart_upload_retried_with_same_key(client, rec):
    rec.add(500, {"error": "boom"}).add(201, {"id": 250})
    client.documents.upload(file=b"%PDF-1.4", filename="deck.pdf")
    assert len(set(keys(rec))) == 1
    assert all(b'filename="deck.pdf"' in r.content for r in rec.requests)


def test_share_derives_link_key(client, rec):
    rec.add(201, {"id": 250}).add(201, {"id": 1, "url": "u"})
    client.share(file_url="https://example.com/a.pdf", request_options={"idempotency_key": "deal-7"})
    assert keys(rec) == ["deal-7", "deal-7:link"]


def test_async_post_retry_same_key(aclient, rec):
    rec.fail(httpx.ConnectError("reset")).add(409, BUSY).add(201, {"id": 9})

    async def run():
        async with aclient as hr:
            return await hr.data_rooms.create(name="Async")

    assert asyncio.run(run())["id"] == 9
    assert len(rec.requests) == 3 and len(set(keys(rec))) == 1
