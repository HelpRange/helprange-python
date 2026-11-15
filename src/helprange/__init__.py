"""Official Python client for the HelpRange API.

>>> from helprange import HelpRange
>>> hr = HelpRange()                       # HELPRANGE_API_KEY
>>> hr.share("deck.pdf", label="ACME")["link"]["url"]
"""
from ._client import DEFAULT_BASE_URL, IN_PROGRESS_MAX_RETRIES, AsyncHelpRange, HelpRange, parse_retry_after
from ._errors import (
    APIConnectionError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    ConflictError,
    HelpRangeError,
    IdempotencyKeyInProgressError,
    IdempotencyKeyReusedError,
    InternalServerError,
    LockedError,
    NotFoundError,
    PayloadTooLargeError,
    PaymentRequiredError,
    PermissionDeniedError,
    RateLimitError,
    UnprocessableEntityError,
    WebhookVerificationError,
)
from ._generated import API_VERSION
from ._types import NOT_GIVEN, NotGiven, RequestOptions
from ._version import __version__
from ._webhooks import DEFAULT_TOLERANCE_SECONDS, compute_signature, sign_webhook_payload, verify_webhook

__all__ = [
    "HelpRange", "AsyncHelpRange", "DEFAULT_BASE_URL", "IN_PROGRESS_MAX_RETRIES", "API_VERSION", "__version__", "parse_retry_after",
    "NOT_GIVEN", "NotGiven", "RequestOptions",
    "verify_webhook", "compute_signature", "sign_webhook_payload", "DEFAULT_TOLERANCE_SECONDS",
    "HelpRangeError", "APIConnectionError", "APITimeoutError", "BadRequestError", "AuthenticationError",
    "PaymentRequiredError", "PermissionDeniedError", "NotFoundError", "ConflictError", "PayloadTooLargeError",
    "LockedError", "RateLimitError", "InternalServerError", "WebhookVerificationError",
    "IdempotencyKeyInProgressError", "UnprocessableEntityError", "IdempotencyKeyReusedError",
]
