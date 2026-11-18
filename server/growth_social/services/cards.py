"""Feishu interactive cards for reply approval.

Cards are built only from fields the service already owns: the post's public
title and source URL, the server score, the rendered draft, and the validated
link. They never contain credentials, raw provider payloads, or hidden prompt
material.
"""

from __future__ import annotations

from typing import Any

from growth_core.schemas import OutreachMessage, OutreachVersion, SocialLead
from growth_social.schemas import IntentScore
from growth_social.services.link_policy import LinkPolicyResult

__all__ = ["build_approval_card"]

_ACTIONS = ("approve", "edit", "reject", "later")
_ACTION_LABELS = {
    "approve": "Approve",
    "edit": "Edit",
    "reject": "Reject",
    "later": "Later",
}
_ACTION_TYPES = {
    "approve": "primary",
    "edit": "default",
    "reject": "danger",
    "later": "default",
}


def _div(content: str) -> dict[str, Any]:
    return {
        "tag": "div",
        "text": {"tag": "lark_md", "content": content},
    }


def _actions(approval_id: str) -> dict[str, Any]:
    return {
        "tag": "action",
        "actions": [
            {
                "tag": "button",
                "text": {
                    "tag": "plain_text",
                    "content": _ACTION_LABELS[action],
                },
                "type": _ACTION_TYPES[action],
                "value": {"approval_id": approval_id, "action": action},
            }
            for action in _ACTIONS
        ],
    }


def build_approval_card(
    *,
    approval_id: str,
    message: OutreachMessage,
    lead: SocialLead,
    version: OutreachVersion,
    score: IntentScore,
    link_policy: LinkPolicyResult,
) -> dict[str, Any]:
    """Build the Feishu interactive approval card for one draft version."""
    community = lead.subreddit or lead.platform
    risk_flags = ", ".join(version.risk_flags) or "none"
    subreddit_result = (
        "links not allowed (manual only)"
        if link_policy.manual_only
        else "links allowed"
    )
    final_link = version.cta_url or link_policy.link_url or ""
    summary = score.summary or "n/a"

    elements: list[dict[str, Any]] = [
        _div(f"**Platform:** {lead.platform}\n**Community:** {community}"),
        _div(f"**Post:** {lead.title}\n**Source:** {lead.source_url}"),
        _div(f"**Score:** {score.score}\n**Why:** {summary}"),
        _div(
            f"**Risk flags:** {risk_flags}\n"
            f"**Subreddit rules:** {subreddit_result}"
        ),
        {
            "tag": "div",
            "text": {"tag": "plain_text", "content": version.body_text},
        },
        _actions(approval_id),
        _div(f"**Final link:** {final_link}"),
    ]

    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "template": "blue",
            "title": {
                "tag": "plain_text",
                "content": "Social reply approval",
            },
        },
        "elements": elements,
    }
