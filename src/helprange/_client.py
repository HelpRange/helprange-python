"""The HelpRange clients: :class:`HelpRange` (sync) and :class:`AsyncHelpRange` (asyncio)."""
from __future__ import annotations

import asyncio
import email.utils
import os
import random
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Tuple

import httpx

from ._errors import (
    APIConnectionError,
    APITimeoutError,
    HelpRangeError,
    IdempotencyKeyInProgressError,
    error_from_response,
)
from ._generated import API_VERSION
from ._generated.models import CreateLinkResponse, FileInput, UploadFileResponse
from ._generated.resources import AsyncResources, Resources
from ._types import RequestOptions
from ._version import __version__

__all__ = ["HelpRange", "AsyncHelpRange", "DEFAULT_BASE_URL", "IN_PROGRESS_MAX_RETRIES", "parse_retry_after"]

DEFAULT_BASE_URL = "https://www.helprange.com"
DEFAULT_TIMEOUT = 60.0
DEFAULT_MAX_RETRIES = 2
#: Longer Retry-After waits (a daily cap, a paused API) are not slept through; the RateLimitError is raised.
DEFAULT_MAX_RETRY_AFTER = 60.0
_RETRYABLE_STATUS = {408, 500, 502, 503, 504}
#: Methods that get an Idempotency-Key (and with it, retries on network errors and 5xx).
_KEYED_METHODS = {"POST", "PATCH"}
#: How often a 409 idempotency_key_in_progress is retried (on top of max_retries, with backoff of ~1-8 s).
IN_PROGRESS_MAX_RETRIES = 5


def parse_retry_after(value: Optional[str], now: Optional[float] = None) -> Optional[float]:
    """Seconds from a Retry-After header (delta-seconds or an HTTP date)."""
    if not value:
        return None
    value = value.strip()
    try:
        return max(0.0, float(value))
    except ValueError:
        pass
    try:
        parsed = email.utils.parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if parsed is None:
        return None
    return max(0.0, parsed.timestamp() - (time.time() if now is None else now))


def _read_file(value: FileInput, filename: Optional[str]) -> Tuple[str, bytes]:
    if isinstance(value, (bytes, bytearray)):
        return filename or "upload", bytes(value)
    if isinstance(value, (str, os.PathLike)):
        path = Path(value)
        return filename or path.name, path.read_bytes()
    data = value.read()
    name = filename or os.path.basename(str(getattr(value, "name", "") or "")) or "upload"
    return name, data


def _form_value(v: Any) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    return str(v)


class _BaseClient:
    def __init__(
        self,
        api_key: Optional[str] = None,
        *,
        base_url: Optional[str] = None,
        timeout: float = DEFAULT_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
        max_retry_after: float = DEFAULT_MAX_RETRY_AFTER,
        default_headers: Optional[Mapping[str, str]] = None,
    ) -> None:
        api_key = api_key or os.environ.get("HELPRANGE_API_KEY")
        if not api_key:
            raise HelpRangeError(
                "No API key: pass api_key=... or set HELPRANGE_API_KEY. Create one in Settings → API keys."
            )
        self._api_key = api_key
        self.base_url = (base_url or os.environ.get("HELPRANGE_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.max_retry_after = max_retry_after
        self._default_headers = dict(default_headers or {})
        #: Usage-limit headers of the latest response: limit, remaining, reset, livemode.
        self.rate_limit: Dict[str, Any] = {}

    api_version = API_VERSION

    @property
    def test_mode(self) -> bool:
        """True for a test-mode key (``hr_test_…``): every call works on your team's sandbox, never on live data."""
        return self._api_key.startswith("hr_test_")

    @property
    def key_hint(self) -> str:
        """The visible start of the key, e.g. ``hr_live_Ab3x…`` (never the whole key)."""
        return self._api_key[:12] + "…"

    def __repr__(self) -> str:
        return f"{type(self).__name__}(key={self.key_hint!r}, base_url={self.base_url!r})"

    # ------------------------------------------------------------------ helpers shared by sync and async

    def _headers(self, method: str, options: Optional[RequestOptions], idempotency_key: Optional[str]) -> Dict[str, str]:
        h = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self._api_key}",
            "User-Agent": f"helprange-python/{__version__}",
            **self._default_headers,
        }
        h.update((options or {}).get("headers") or {})
        # One Idempotency-Key per call, the same for every retry: the API runs the request once and replays the answer.
        key = idempotency_key or (options or {}).get("idempotency_key")
        existing = [k for k in h if k.lower() == "idempotency-key"]
        if key:
            for k in existing:
                del h[k]
            h["Idempotency-Key"] = key
        elif not existing and method in _KEYED_METHODS:
            h["Idempotency-Key"] = str(uuid.uuid4())
        return h

    def _build(
        self,
        method: str,
        path: str,
        params: Optional[Dict[str, Any]],
        json: Optional[Dict[str, Any]],
        file_field: Optional[str],
        options: Optional[RequestOptions],
        idempotency_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        kwargs: Dict[str, Any] = {
            "method": method,
            "url": self.base_url + path,
            "headers": self._headers(method, options, idempotency_key),
            "timeout": (options or {}).get("timeout", self.timeout),
        }
        if params:
            kwargs["params"] = {k: _form_value(v) if isinstance(v, bool) else v for k, v in params.items()}
        if json is not None and method != "GET":
            body = dict(json)
            file = body.pop(file_field, None) if file_field else None
            if file is not None:
                name, data = _read_file(file, body.get("filename"))
                kwargs["files"] = {file_field: (name, data)}
                kwargs["data"] = {k: _form_value(v) for k, v in body.items()}
            else:
                kwargs["json"] = body
        return kwargs

    def _track(self, headers: httpx.Headers) -> None:
        def num(name: str) -> Optional[int]:
            v = headers.get(name)
            return int(v) if v is not None and v.isdigit() else None

        live = headers.get("x-helprange-livemode")
        self.rate_limit = {
            "limit": num("x-ratelimit-limit"),
            "remaining": num("x-ratelimit-remaining"),
            "reset": num("x-ratelimit-reset"),
            "livemode": None if live is None else live == "true",
        }

    @staticmethod
    def _parse(response: httpx.Response) -> Any:
        if not response.content:
            return {}
        ctype = response.headers.get("content-type", "")
        text = response.text
        if "json" in ctype or text.lstrip()[:1] in ("{", "["):
            try:
                return response.json()
            except ValueError:
                return text
        return text

    @staticmethod
    def _retry_safe(method: str, headers: Mapping[str, str]) -> bool:
        """GETs, and writes that carry an Idempotency-Key, can be sent again after a network error or a 5xx."""
        return method == "GET" or any(k.lower() == "idempotency-key" for k in headers)

    def _in_progress_delay(self, in_progress: int, response: httpx.Response) -> float:
        wait = parse_retry_after(response.headers.get("retry-after"))
        return wait if wait is not None and wait <= self.max_retry_after else self._backoff(in_progress)

    def _retry_delay(self, attempt: int, safe: bool, response: Optional[httpx.Response], body: Any) -> Optional[float]:
        """Seconds to wait before the next attempt, or None when the error must be raised."""
        if response is None:  # connection error / timeout
            return self._backoff(attempt) if safe else None
        status = response.status_code
        wait = parse_retry_after(response.headers.get("retry-after"))
        if status == 429:  # the API did not carry out the request, so a retry is safe for any method
            if wait is None and isinstance(body, dict) and isinstance(body.get("retry_after"), (int, float)):
                wait = float(body["retry_after"])
            if wait is None:
                return self._backoff(attempt)
            return wait if wait <= self.max_retry_after else None
        if safe and status in _RETRYABLE_STATUS:
            return wait if wait is not None and wait <= self.max_retry_after else self._backoff(attempt)
        return None

    @staticmethod
    def _backoff(attempt: int) -> float:
        return min(8.0, 0.5 * 2**attempt) * (0.75 + random.random() * 0.25)


class HelpRange(_BaseClient, Resources):
    """Synchronous HelpRange API client.

    >>> from helprange import HelpRange
    >>> hr = HelpRange()  # reads HELPRANGE_API_KEY
    >>> hr.documents.list()["documents"]

    Resources mirror the tags of the API reference: ``account``, ``folders``, ``documents``, ``links``, ``triggers``,
    ``data_rooms`` (with ``guests``, ``documents``, ``folders``, … sub-resources), ``ndas``, ``signature_requests``,
    ``offers``, ``store``, ``lead_forms``, ``activity``, ``webhook_endpoints``.
    Responses are plain dicts typed with TypedDicts from :mod:`helprange.types`.

    :param api_key: team API key (``hr_live_…`` / ``hr_test_…``); default ``HELPRANGE_API_KEY``.
    :param base_url: API origin; default ``https://www.helprange.com`` (or ``HELPRANGE_BASE_URL``).
    :param timeout: seconds per attempt (default 60).
    :param max_retries: retries of a failed request (default 2) – see README → Retries.
    :param http_client: your own ``httpx.Client`` (proxies, custom transports, tests).
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        *,
        base_url: Optional[str] = None,
        timeout: float = DEFAULT_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
        max_retry_after: float = DEFAULT_MAX_RETRY_AFTER,
        default_headers: Optional[Mapping[str, str]] = None,
        http_client: Optional[httpx.Client] = None,
    ) -> None:
        super().__init__(api_key, base_url=base_url, timeout=timeout, max_retries=max_retries,
                         max_retry_after=max_retry_after, default_headers=default_headers)
        self._http = http_client or httpx.Client(follow_redirects=False)
        self._own_http = http_client is None
        self._init_resources()

    def request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        json: Optional[Dict[str, Any]] = None,
        request_options: Optional[RequestOptions] = None,
    ) -> Any:
        """Sends a request to any endpoint (for ones this SDK version does not wrap yet) and returns the JSON."""
        return self._request(method.upper(), path, params=params, json=json, options=request_options)

    def _request(self, method: str, path: str, *, params: Optional[Dict[str, Any]] = None,
                 json: Optional[Dict[str, Any]] = None, file_field: Optional[str] = None,
                 options: Optional[RequestOptions] = None, idempotency_key: Optional[str] = None) -> Any:
        kwargs = self._build(method, path, params, json, file_field, options, idempotency_key)
        max_retries = (options or {}).get("max_retries", self.max_retries)
        safe = self._retry_safe(method, kwargs["headers"])
        attempt = in_progress = 0
        response: Optional[httpx.Response]
        body: Any
        while True:
            try:
                resp = self._http.request(**kwargs)
            except httpx.TimeoutException as exc:
                error: HelpRangeError = APITimeoutError(f"Request timed out after {kwargs['timeout']} s.")
                error.__cause__ = exc
                response, body = None, None
            except httpx.TransportError as exc:
                error = APIConnectionError(f"Connection error: {exc}")
                error.__cause__ = exc
                response, body = None, None
            else:
                response, body = resp, self._parse(resp)
                self._track(resp.headers)
                if resp.is_success:
                    return body
                error = error_from_response(resp.status_code, body, resp.headers)
                if (isinstance(error, IdempotencyKeyInProgressError) and max_retries > 0
                        and in_progress < IN_PROGRESS_MAX_RETRIES):
                    # the first request with this key is still running; once it finishes the API replays its answer
                    in_progress += 1
                    time.sleep(self._in_progress_delay(in_progress, resp))
                    continue  # does not use up max_retries
            delay = self._retry_delay(attempt, safe, response, body) if attempt < max_retries else None
            if delay is None:
                raise error
            time.sleep(delay)
            attempt += 1

    def share(
        self,
        file: Optional[FileInput] = None,
        *,
        filename: Optional[str] = None,
        folder_id: Optional[int] = None,
        file_url: Optional[str] = None,
        request_options: Optional[RequestOptions] = None,
        **link: Any,
    ) -> Dict[str, Any]:
        """Uploads a file (or a public ``file_url``) and creates a share link for it in one call.

        Keyword arguments other than the upload ones are the link settings of
        :meth:`Documents.create_link <helprange.resources.Documents.create_link>` (``label``, ``allow_download``,
        ``passcode``, ``expires_on``, ``views_limit``, ``watermark``, ``require_email``, ``disallow_forwarding``,
        ``one_viewer_at_a_time``).

        :returns: ``{"document": <uploaded document>, "link": <share link>}``

        >>> hr.share("deck.pdf", label="ACME - Anna", allow_download=False)["link"]["url"]
        """
        document: UploadFileResponse = self.documents.upload(
            file=file, filename=filename, folder_id=folder_id, file_url=file_url, request_options=request_options
        )
        # with an idempotency_key both calls stay idempotent: the upload uses the key, the link "<key>:link"
        link_options = request_options
        if request_options and request_options.get("idempotency_key"):
            link_options = {**request_options, "idempotency_key": f"{request_options['idempotency_key']}:link"}
        created: CreateLinkResponse = self.documents.create_link(document["id"], request_options=link_options, **link)
        return {"document": document, "link": created}

    def close(self) -> None:
        """Closes the HTTP connection pool (if the client created it)."""
        if self._own_http:
            self._http.close()

    def __enter__(self) -> "HelpRange":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()


class AsyncHelpRange(_BaseClient, AsyncResources):
    """Asyncio HelpRange API client – the same resources as :class:`HelpRange`, every method awaitable.

    >>> async with AsyncHelpRange() as hr:
    ...     rooms = await hr.data_rooms.list()
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        *,
        base_url: Optional[str] = None,
        timeout: float = DEFAULT_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
        max_retry_after: float = DEFAULT_MAX_RETRY_AFTER,
        default_headers: Optional[Mapping[str, str]] = None,
        http_client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        super().__init__(api_key, base_url=base_url, timeout=timeout, max_retries=max_retries,
                         max_retry_after=max_retry_after, default_headers=default_headers)
        self._http = http_client or httpx.AsyncClient(follow_redirects=False)
        self._own_http = http_client is None
        self._init_resources()

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        json: Optional[Dict[str, Any]] = None,
        request_options: Optional[RequestOptions] = None,
    ) -> Any:
        """Sends a request to any endpoint and returns the JSON."""
        return await self._request(method.upper(), path, params=params, json=json, options=request_options)

    async def _request(self, method: str, path: str, *, params: Optional[Dict[str, Any]] = None,
                       json: Optional[Dict[str, Any]] = None, file_field: Optional[str] = None,
                       options: Optional[RequestOptions] = None, idempotency_key: Optional[str] = None) -> Any:
        kwargs = self._build(method, path, params, json, file_field, options, idempotency_key)
        max_retries = (options or {}).get("max_retries", self.max_retries)
        safe = self._retry_safe(method, kwargs["headers"])
        attempt = in_progress = 0
        response: Optional[httpx.Response]
        body: Any
        while True:
            try:
                resp = await self._http.request(**kwargs)
            except httpx.TimeoutException as exc:
                error: HelpRangeError = APITimeoutError(f"Request timed out after {kwargs['timeout']} s.")
                error.__cause__ = exc
                response, body = None, None
            except httpx.TransportError as exc:
                error = APIConnectionError(f"Connection error: {exc}")
                error.__cause__ = exc
                response, body = None, None
            else:
                response, body = resp, self._parse(resp)
                self._track(resp.headers)
                if resp.is_success:
                    return body
                error = error_from_response(resp.status_code, body, resp.headers)
                if (isinstance(error, IdempotencyKeyInProgressError) and max_retries > 0
                        and in_progress < IN_PROGRESS_MAX_RETRIES):
                    # the first request with this key is still running; once it finishes the API replays its answer
                    in_progress += 1
                    await asyncio.sleep(self._in_progress_delay(in_progress, resp))
                    continue  # does not use up max_retries
            delay = self._retry_delay(attempt, safe, response, body) if attempt < max_retries else None
            if delay is None:
                raise error
            await asyncio.sleep(delay)
            attempt += 1

    async def share(
        self,
        file: Optional[FileInput] = None,
        *,
        filename: Optional[str] = None,
        folder_id: Optional[int] = None,
        file_url: Optional[str] = None,
        request_options: Optional[RequestOptions] = None,
        **link: Any,
    ) -> Dict[str, Any]:
        """Async :meth:`HelpRange.share`: upload a file and create a share link."""
        document = await self.documents.upload(
            file=file, filename=filename, folder_id=folder_id, file_url=file_url, request_options=request_options
        )
        # with an idempotency_key both calls stay idempotent: the upload uses the key, the link "<key>:link"
        link_options = request_options
        if request_options and request_options.get("idempotency_key"):
            link_options = {**request_options, "idempotency_key": f"{request_options['idempotency_key']}:link"}
        created = await self.documents.create_link(document["id"], request_options=link_options, **link)
        return {"document": document, "link": created}

    async def close(self) -> None:
        if self._own_http:
            await self._http.aclose()

    async def __aenter__(self) -> "AsyncHelpRange":
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.close()
