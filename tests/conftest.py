"""Fake transport for the tests – no request ever leaves the process."""
import json
from typing import Any, Callable, List, Union

import httpx
import pytest

import helprange

KEY = "hr_live_" + "x" * 40


class Recorder:
    """Queue of canned responses; records every request."""

    def __init__(self) -> None:
        self.queue: List[Union[httpx.Response, Exception, Callable[[httpx.Request], httpx.Response]]] = []
        self.requests: List[httpx.Request] = []

    def add(self, status: int = 200, body: Any = None, headers: Any = None) -> "Recorder":
        content = body if isinstance(body, (bytes, str)) else json.dumps({} if body is None else body)
        h = {"content-type": "application/json", **(headers or {})}
        self.queue.append(httpx.Response(status, content=content, headers=h))
        return self

    def fail(self, exc: Exception) -> "Recorder":
        self.queue.append(exc)
        return self

    def __call__(self, request: httpx.Request) -> httpx.Response:
        request.read()
        self.requests.append(request)
        if not self.queue:
            raise AssertionError(f"unexpected request {request.method} {request.url}")
        nxt = self.queue.pop(0)
        if isinstance(nxt, Exception):
            raise nxt
        if callable(nxt):
            return nxt(request)
        return nxt

    def json(self, i: int = -1) -> Any:
        return json.loads(self.requests[i].content)


@pytest.fixture
def rec() -> Recorder:
    return Recorder()


@pytest.fixture
def client(rec: Recorder) -> helprange.HelpRange:
    return helprange.HelpRange(KEY, http_client=httpx.Client(transport=httpx.MockTransport(rec)))


@pytest.fixture
def aclient(rec: Recorder) -> helprange.AsyncHelpRange:
    return helprange.AsyncHelpRange(KEY, http_client=httpx.AsyncClient(transport=httpx.MockTransport(rec)))


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    """Retries back off with time.sleep / asyncio.sleep – make them instant."""
    import asyncio
    import time

    async def fast_async_sleep(_: float) -> None:
        return None

    monkeypatch.setattr(time, "sleep", lambda _: None)
    monkeypatch.setattr(asyncio, "sleep", fast_async_sleep)
