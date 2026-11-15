"""Verification helpers for Feishu (Lark) event callbacks.

Feishu signs callbacks with::

    sha256((timestamp + nonce + encrypt_key).encode("utf-8") + body)

and sends the hex digest in ``X-Lark-Signature``. URL-verification callbacks
carry a plain verification token either in ``header.token`` (event schema
v2) or at the top level of the payload.
"""

from __future__ import annotations

import hashlib
import hmac
from collections.abc import Mapping
from typing import Any

__all__ = ["verify_feishu_signature", "verify_feishu_token"]

_SIGNATURE_HEADER = "x-lark-signature"
_TIMESTAMP_HEADER = "x-lark-request-timestamp"
_NONCE_HEADER = "x-lark-request-nonce"


def _get_header(headers: Mapping[str, str], name: str) -> str:
    """Look up a header case-insensitively, returning ``""`` when absent."""
    value = headers.get(name)
    if value is not None:
        return value
    lowered = name.lower()
    for key, candidate in headers.items():
        if key.lower() == lowered:
            return candidate
    return ""


def verify_feishu_signature(
    headers: Mapping[str, str], body: bytes, encrypt_key: str
) -> bool:
    """Return ``True`` when ``body`` matches the Feishu request signature."""
    if not encrypt_key:
        return False
    timestamp = _get_header(headers, _TIMESTAMP_HEADER)
    nonce = _get_header(headers, _NONCE_HEADER)
    signature = _get_header(headers, _SIGNATURE_HEADER)
    if not timestamp or not nonce or not signature:
        return False

    expected = hashlib.sha256(
        (timestamp + nonce + encrypt_key).encode("utf-8") + body
    ).hexdigest()
    return hmac.compare_digest(
        expected.encode("utf-8"), signature.encode("utf-8")
    )


def verify_feishu_token(payload: dict[str, Any], expected_token: str) -> bool:
    """Return ``True`` when the callback payload carries the expected token.

    Event schema v2 puts the token in ``payload["header"]["token"]``; URL
    verification challenges put it at the top level. The header token wins
    when both are present so a payload cannot downgrade to the weaker field.
    An empty expected token always fails closed.
    """
    if not expected_token:
        return False

    supplied: Any = None
    header = payload.get("header")
    if isinstance(header, Mapping):
        supplied = header.get("token")
    if not isinstance(supplied, str) or not supplied:
        supplied = payload.get("token")

    if not isinstance(supplied, str) or not supplied:
        return False
    return hmac.compare_digest(
        supplied.encode("utf-8"), expected_token.encode("utf-8")
    )
