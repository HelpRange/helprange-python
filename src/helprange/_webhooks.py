"""Webhook signature verification (the same scheme as HelpRange's own ``plus/webhooks.verify``)."""
from __future__ import annotations

import hashlib
import hmac
import json
import time
from typing import Any, Dict, Mapping, Optional, Sequence, Union

from ._errors import WebhookVerificationError

__all__ = ["verify_webhook", "compute_signature", "sign_webhook_payload", "DEFAULT_TOLERANCE_SECONDS"]

#: Default tolerance of the signature timestamp, in seconds.
DEFAULT_TOLERANCE_SECONDS = 300


def _bytes(payload: Union[bytes, bytearray, str]) -> bytes:
    return payload.encode("utf-8") if isinstance(payload, str) else bytes(payload)


def compute_signature(payload: Union[bytes, str], secret: str, timestamp: int) -> str:
    """Hex HMAC-SHA256 of ``"<timestamp>.<raw body>"`` – the ``v1`` value of ``HelpRange-Signature``."""
    return hmac.new(secret.encode(), str(int(timestamp)).encode() + b"." + _bytes(payload), hashlib.sha256).hexdigest()


def sign_webhook_payload(payload: Union[bytes, str], secret: str, timestamp: Optional[int] = None) -> str:
    """Builds a ``HelpRange-Signature`` header value (``t=<unix>,v1=<hex>``) – handy in tests of your handler."""
    ts = int(time.time() if timestamp is None else timestamp)
    return f"t={ts},v1={compute_signature(payload, secret, ts)}"


def _header(headers: Any, name: str) -> Optional[str]:
    getter = getattr(headers, "get", None)
    value = None
    if getter is not None:
        value = getter(name)
    if value is None:
        wanted = name.lower()
        for k, v in headers.items():
            if str(k).lower() == wanted:
                value = v
                break
    if isinstance(value, (list, tuple)):
        value = value[0] if value else None
    return value


def verify_webhook(
    payload: Union[bytes, str],
    headers: Union[Mapping[str, Any], Any],
    secret: Union[str, Sequence[str]],
    *,
    tolerance: int = DEFAULT_TOLERANCE_SECONDS,
    now: Optional[float] = None,
) -> Dict[str, Any]:
    """Verifies a HelpRange webhook and returns the parsed event.

    HelpRange signs each delivery with ``HelpRange-Signature: t=<unix seconds>,v1=<hex HMAC-SHA256(secret,
    "<t>.<raw body>")>``. For 24 hours after a secret rotation the header carries a second ``v1=`` signed with the
    previous secret; any match is accepted. The timestamp must be within ``tolerance`` seconds of now.

    :param payload: the **raw** request body (bytes as received – e.g. ``request.body`` in Django,
        ``request.get_data()`` in Flask, ``await request.body()`` in FastAPI), not re-serialised JSON.
    :param headers: request headers – a dict, ``request.headers`` of Django / Flask / Starlette, or an
        ``http.server`` message; names are case-insensitive.
    :param secret: the endpoint's signing secret (``whsec_…``), or several during your own rotation.
    :raises WebhookVerificationError: missing / malformed header, stale timestamp, no matching signature, bad JSON.
    """
    header = _header(headers, "HelpRange-Signature")
    if not header:
        raise WebhookVerificationError("Missing HelpRange-Signature header.")
    parts = [tuple(p.strip() for p in item.split("=", 1)) for item in header.split(",") if "=" in item]
    ts = next((v for k, v in parts if k == "t"), None)
    if ts is None or not ts.isdigit():
        raise WebhookVerificationError("HelpRange-Signature has no valid timestamp.")
    current = time.time() if now is None else now
    if abs(current - int(ts)) > tolerance:
        raise WebhookVerificationError(f"Webhook timestamp is outside the tolerance of {tolerance} seconds.")
    secrets = [secret] if isinstance(secret, str) else [s for s in secret]
    secrets = [s for s in secrets if s]
    if not secrets:
        raise WebhookVerificationError("No webhook secret given.")
    body = _bytes(payload)
    candidates = [v for k, v in parts if k == "v1"]
    expected = [compute_signature(body, s, int(ts)).encode() for s in secrets]
    if not any(hmac.compare_digest(c.encode("utf-8"), e) for e in expected for c in candidates):
        raise WebhookVerificationError("No HelpRange-Signature v1 signature matches the payload.")
    try:
        return json.loads(body.decode("utf-8"))
    except ValueError as exc:
        raise WebhookVerificationError("Webhook payload is not valid JSON.") from exc
