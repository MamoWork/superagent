"""Helpers for deciding whether a public author can be tracked.

Sources expose deleted or anonymised authors as an empty string or the literal
``"[deleted]"`` (Reddit). Every such lead shares the same string, so keying a
platform-user suppression or a same-author lookup on it would block the wrong
people. Only a real, non-empty identifier is contactable.
"""

from __future__ import annotations

__all__ = ["is_contactable_author"]

_DELETED_AUTHOR = "[deleted]"


def is_contactable_author(author_public: str | None) -> bool:
    """Return ``True`` when ``author_public`` identifies one specific author."""
    if author_public is None:
        return False
    normalized = author_public.strip()
    return bool(normalized) and normalized.lower() != _DELETED_AUTHOR
