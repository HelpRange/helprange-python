"""Small shared types: the NOT_GIVEN sentinel and per-request options."""
from __future__ import annotations

from typing import Any, Dict, Iterable, Mapping, TypedDict, Union
from urllib.parse import quote


class NotGiven:
    """Marks an argument that was not passed, for fields where ``None`` means JSON ``null``.

    Example: ``folders.move_documents(31, document_ids=[1], subfolder_id=None)`` takes the documents out of their
    subfolder, while leaving ``subfolder_id`` out does not send it at all.
    """

    _instance = None

    def __new__(cls) -> "NotGiven":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __bool__(self) -> bool:
        return False

    def __repr__(self) -> str:
        return "NOT_GIVEN"


NOT_GIVEN = NotGiven()


class RequestOptions(TypedDict, total=False):
    """Per-request overrides, passed as ``request_options=`` to any resource method."""

    timeout: float
    """Timeout of each attempt in seconds."""
    max_retries: int
    """Retries for this request."""
    headers: Dict[str, str]
    """Extra HTTP headers."""
    idempotency_key: str
    """Idempotency-Key of a POST / PATCH (default: a new UUID v4 per call, reused by its retries)."""


def _clean(values: Mapping[str, Any], keep_none: Iterable[str] = ()) -> Dict[str, Any]:
    """Drops arguments that were not given (NOT_GIVEN, and None unless the field is nullable)."""
    keep = set(keep_none)
    return {k: v for k, v in values.items() if v is not NOT_GIVEN and (v is not None or k in keep)}


def _path(value: Union[str, int]) -> str:
    """Encodes one path parameter."""
    return quote(str(value), safe="")
