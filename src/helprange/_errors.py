"""Exceptions. Every exception the SDK raises is a :class:`HelpRangeError`."""
from __future__ import annotations

from typing import Any, Dict, Optional, Type

import httpx

__all__ = [
    "HelpRangeError", "APIConnectionError", "APITimeoutError", "BadRequestError", "AuthenticationError",
    "PaymentRequiredError", "PermissionDeniedError", "NotFoundError", "ConflictError", "PayloadTooLargeError",
    "LockedError", "RateLimitError", "InternalServerError", "WebhookVerificationError",
    "IdempotencyKeyInProgressError", "UnprocessableEntityError", "IdempotencyKeyReusedError",
]


class HelpRangeError(Exception):
    """Base class. HTTP errors carry ``status``, the API's machine-readable ``code`` and the parsed ``body``."""

    def __init__(
        self,
        message: str,
        *,
        status: Optional[int] = None,
        code: Optional[str] = None,
        body: Any = None,
        headers: Optional[httpx.Headers] = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status = status
        self.code = code
        self.body = body
        self.headers = headers

    def __str__(self) -> str:
        bits = [str(self.status)] if self.status else []
        if self.code:
            bits.append(self.code)
        return f"[{' '.join(bits)}] {self.message}" if bits else self.message


class APIConnectionError(HelpRangeError):
    """The request never got an HTTP answer (DNS, TCP, TLS, reset…)."""


class APITimeoutError(APIConnectionError):
    """An attempt took longer than the timeout."""


class BadRequestError(HelpRangeError):
    """400 – the request was refused (missing field, duplicate link label, ``sandbox_email_domain``…)."""


class AuthenticationError(HelpRangeError):
    """401 – missing, unknown, revoked or expired key (``invalid_key``, ``key_revoked``, ``key_expired``, ``key_owner_removed``)."""


class PaymentRequiredError(HelpRangeError):
    """402 – the team's plan does not include the REST API or this feature."""


class PermissionDeniedError(HelpRangeError):
    """403 – no permission; with ``code == "insufficient_scope"`` the key lacks :attr:`required_scope`."""

    @property
    def required_scope(self) -> Optional[str]:
        return self.body.get("required_scope") if isinstance(self.body, dict) else None


class NotFoundError(HelpRangeError):
    """404 – no such object, or not visible to this key."""


class ConflictError(HelpRangeError):
    """409 – conflict (a frozen data room, a signed PDF not ready yet, the team already has a webhook endpoint…)."""


class IdempotencyKeyInProgressError(ConflictError):
    """409 ``idempotency_key_in_progress`` – a request with the same Idempotency-Key is still running.

    The client retries these with backoff; you only see it when the first request keeps running past those retries.
    """


class UnprocessableEntityError(HelpRangeError):
    """422 – the request was understood but cannot be processed."""


class IdempotencyKeyReusedError(UnprocessableEntityError):
    """422 ``idempotency_key_reused`` – the key was used in the last 24 hours for a different request (method, path or
    body). Use a new key for a new request; never retried."""


class PayloadTooLargeError(HelpRangeError):
    """413 – file or request too large (``FILE_TOO_LARGE``, ``REQUEST_TOO_LARGE``)."""


class LockedError(HelpRangeError):
    """423 – the object is locked, e.g. a frozen data room (``ROOM_FROZEN``)."""


class RateLimitError(HelpRangeError):
    """429 – a usage limit was reached (``RATE_LIMITED``, ``DAILY_LIMIT``, ``PAUSED``, ``UPLOAD_LIMIT``)."""

    @property
    def retry_after(self) -> Optional[int]:
        """Seconds to wait before retrying."""
        if isinstance(self.body, dict) and isinstance(self.body.get("retry_after"), int):
            return self.body["retry_after"]
        value = self.headers.get("retry-after") if self.headers is not None else None
        return int(value) if value and value.isdigit() else None


class InternalServerError(HelpRangeError):
    """5xx – HelpRange had a problem."""


class WebhookVerificationError(HelpRangeError):
    """:func:`verify_webhook` rejected the payload (bad or missing signature, stale timestamp, not JSON)."""


_BY_STATUS: Dict[int, Type[HelpRangeError]] = {
    400: BadRequestError,
    401: AuthenticationError,
    402: PaymentRequiredError,
    403: PermissionDeniedError,
    404: NotFoundError,
    409: ConflictError,
    413: PayloadTooLargeError,
    422: UnprocessableEntityError,
    423: LockedError,
    429: RateLimitError,
}


def error_from_response(status: int, body: Any, headers: httpx.Headers) -> HelpRangeError:
    """Builds the right exception for an error response (v2 ``{error, code}`` and the v1 shapes)."""
    message, code = f"HTTP {status}", None
    if isinstance(body, dict):
        for key in ("error", "message", "reason", "detail"):
            if isinstance(body.get(key), str) and body[key]:
                message = body[key]
                break
        if isinstance(body.get("code"), str):
            code = body["code"]
    elif isinstance(body, str) and body.strip():
        message = body.strip()[:500]
    cls = _BY_STATUS.get(status) or (InternalServerError if status >= 500 else HelpRangeError)
    if status == 409 and code == "idempotency_key_in_progress":
        cls = IdempotencyKeyInProgressError
    elif status == 422 and code == "idempotency_key_reused":
        cls = IdempotencyKeyReusedError
    return cls(message, status=status, code=code, body=body, headers=headers)
