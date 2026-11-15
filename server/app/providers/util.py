from __future__ import annotations

import hashlib
import html
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def make_signal_id(provider_id: str, url: str, title: str) -> str:
    return hashlib.sha256(
        f"{provider_id}|{url}|{title}".encode("utf-8")
    ).hexdigest()[:24]


def strip_html(value: object, limit: int = 2000) -> str:
    if value is None:
        return ""
    text = html.unescape(_TAG_RE.sub(" ", str(value)))
    text = _WS_RE.sub(" ", text).strip()
    return text[:limit]


def parse_datetime(value: object) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = parsedate_to_datetime(text)
        except (TypeError, ValueError, OverflowError):
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def sort_timestamp(value: object) -> float:
    parsed = parse_datetime(value)
    if parsed is None:
        return 0.0
    return (parsed - _EPOCH).total_seconds()
