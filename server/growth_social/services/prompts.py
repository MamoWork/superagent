"""Server-side prompt rendering helpers.

Prompts use :class:`string.Template` placeholders (``$title``, ``$body``, ...).
Rendering happens on the server so the values sent to the model are exactly the
values the service holds. This module performs no LLM calls and logs nothing.
"""

from __future__ import annotations

import string

__all__ = ["render_user_prompt"]


def render_user_prompt(template: str, /, **values: object) -> str:
    """Substitute ``$name`` placeholders in ``template`` with ``values``.

    Uses :meth:`string.Template.safe_substitute` so an unknown placeholder is
    left untouched rather than raising. The caller decides which values are
    safe to send; nothing here reads configuration or calls a provider.
    """
    return string.Template(template).safe_substitute(**values)
