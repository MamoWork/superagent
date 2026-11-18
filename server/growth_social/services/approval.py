"""Feishu approval callbacks and operator revision of a draft.

Approval is the only human decision point in the social pipeline. This module
turns a Feishu card action into a compare-and-set state transition, and lets an
operator revise a draft, which creates a new immutable version, expires the old
approval cards, and enqueues a fresh approval card.

Approval only moves database state. Nothing here posts, comments, or DMs: that
stays a separate, manually triggered step.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import UUID

from growth_core.config import GrowthSettings
from growth_core.repositories.base import GrowthRepository
from growth_core.schemas import (
    ApprovalRequest,
    NewApprovalRequest,
    NewAuditEntry,
    NewOutboxMessage,
    OutreachMessage,
    OutreachVersion,
    SocialLead,
)
from growth_social.schemas import IntentScore
from growth_social.services.cards import build_approval_card
from growth_social.services.link_policy import (
    LinkPolicyConfig,
    validate_link_policy,
)

__all__ = [
    "ApprovalResult",
    "FeishuAction",
    "ensure_approval_and_enqueue_card",
    "handle_approval",
    "parse_feishu_action",
    "subreddit_allows_links",
]

_APPROVAL_ACTIONS = frozenset({"approve", "reject", "edit", "later"})
_SCORED_STATUSES = frozenset({"qualified", "watch", "dropped"})
_INVALID_ACTION = "INVALID_FEISHU_ACTION"

_EDIT_REASON = "Edit this draft in the Admin UI to revise it."
_LATER_REASON = "Reminder: this approval is still pending."


@dataclass(frozen=True)
class FeishuAction:
    """One card action parsed from a Feishu callback payload."""

    approval_id: str
    action: Literal["approve", "reject", "edit", "later"]
    operator: str | None = None


@dataclass(frozen=True)
class ApprovalResult:
    """Outcome of applying a Feishu action to an approval."""

    status: Literal[
        "approved", "rejected", "pending", "already_decided", "not_found"
    ]
    message_id: UUID | None = None
    reason: str = ""


def _clock(now: datetime | None) -> datetime:
    return datetime.now(timezone.utc) if now is None else now


def _card_score(lead: SocialLead) -> IntentScore:
    status = lead.status if lead.status in _SCORED_STATUSES else "watch"
    return IntentScore(
        score=lead.score or 0,
        status=status,
        dimensions=[],
        penalties=[],
        summary="",
    )


def subreddit_allows_links(lead: SocialLead) -> bool:
    """Link allowance follows the configured rule's truthiness.

    Fail closed: a missing ``self_promotion_allowed`` key defaults to *not*
    allowed, so an unconfigured subreddit can never produce a sendable draft.
    Only the JSON boolean ``true`` allows links; ``None``, ``0``, ``""``,
    ``False`` and non-boolean strings (including ``"false"``) are denied.
    """
    return lead.subreddit_rules.get("self_promotion_allowed") is True


async def ensure_approval_and_enqueue_card(
    repo: GrowthRepository,
    *,
    tenant_id: UUID,
    workspace_id: UUID,
    message: OutreachMessage,
    approval_id: str,
    lead: SocialLead,
    version: OutreachVersion,
    settings: GrowthSettings,
    clock: datetime,
) -> ApprovalRequest:
    """Idempotently ensure the approval row and its card outbox row exist.

    Both writes are keyed by ``approval_id`` so retries and concurrent calls
    converge on one approval and one ``feishu:{approval_id}`` outbox row. The
    card is always rebuilt from ``version.body_text``, which is the immutable
    text that was validated when the version was created.
    """
    approval = await repo.get_approval_request(tenant_id, approval_id)
    if approval is None:
        approval = await repo.create_approval_request(
            NewApprovalRequest(
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                message_id=message.id,
                approval_id=approval_id,
                provider="feishu",
                payload={"chat_id": settings.feishu_chat_id},
            )
        )

    policy = validate_link_policy(
        version.body_text,
        LinkPolicyConfig(allowed_domain=settings.product_domain),
        subreddit_allows_links=subreddit_allows_links(lead),
    )
    card = build_approval_card(
        approval_id=approval_id,
        message=message,
        lead=lead,
        version=version,
        score=_card_score(lead),
        link_policy=policy,
    )
    await repo.enqueue_outbox(
        NewOutboxMessage(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            topic="feishu.card",
            payload={
                "chat_id": settings.feishu_chat_id,
                "card": card,
                "approval_id": approval_id,
            },
            idempotency_key=f"feishu:{approval_id}",
            next_attempt_at=clock,
        )
    )
    return approval


def _action_value(payload: Mapping[str, Any]) -> Any:
    """Return the card action value from the current or legacy shape."""
    event = payload.get("event")
    if isinstance(event, Mapping):
        action_block = event.get("action")
    else:
        action_block = payload.get("action")
    if not isinstance(action_block, Mapping):
        return None
    value: Any = action_block.get("value")
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (TypeError, ValueError):
            return None
    return value


def _operator(payload: Mapping[str, Any]) -> str | None:
    event = payload.get("event")
    if isinstance(event, Mapping):
        operator = event.get("operator")
        if isinstance(operator, Mapping):
            operator_id = operator.get("operator_id")
            if isinstance(operator_id, Mapping):
                open_id = operator_id.get("open_id")
                if isinstance(open_id, str) and open_id:
                    return open_id
    open_id = payload.get("open_id")
    return open_id if isinstance(open_id, str) and open_id else None


def parse_feishu_action(payload: dict[str, Any]) -> FeishuAction:
    """Parse a Feishu card callback into a :class:`FeishuAction`.

    Supports the current ``event.action.value`` shape and the legacy top-level
    ``action.value`` shape. Any missing or unknown field raises
    ``ValueError("INVALID_FEISHU_ACTION")``.
    """
    value = _action_value(payload)
    if not isinstance(value, Mapping):
        raise ValueError(_INVALID_ACTION)
    approval_id = value.get("approval_id")
    action = value.get("action")
    if (
        not isinstance(approval_id, str)
        or not approval_id
        or not isinstance(action, str)
        or action not in _APPROVAL_ACTIONS
    ):
        raise ValueError(_INVALID_ACTION)
    return FeishuAction(
        approval_id=approval_id,
        action=action,  # type: ignore[arg-type]
        operator=_operator(payload),
    )


def _audit(
    *,
    tenant_id: UUID,
    workspace_id: UUID | None,
    actor_type: Literal["user", "service", "n8n", "system"],
    actor_id: str | None,
    action: str,
    message_id: UUID,
    after: dict[str, Any] | None = None,
) -> NewAuditEntry:
    return NewAuditEntry(
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        actor_type=actor_type,
        actor_id=actor_id,
        action=action,
        entity_type="outreach_message",
        entity_id=message_id,
        after=after,
    )


def _approval_version(approval_id: str) -> int | None:
    """Return the ``N`` from an ``<message-id>:vN`` approval id, else ``None``."""
    try:
        prefix, suffix = approval_id.rsplit(":v", 1)
    except ValueError:
        return None
    if not prefix:
        return None
    try:
        value = int(suffix)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


async def _approve(
    repo: GrowthRepository,
    *,
    tenant_id: UUID,
    approval: ApprovalRequest,
    decided_by: str,
    clock: datetime,
) -> ApprovalResult:
    decided = await repo.decide_approval(
        tenant_id, approval.approval_id, "approved", decided_by
    )
    if not decided:
        return ApprovalResult("already_decided", approval.message_id)
    moved = await repo.update_message_status(
        tenant_id, approval.message_id, "draft_ready", "approved"
    )
    if not moved:
        # The approval row now says approved but the message was not in a
        # sendable state. Do not stamp a version the operator did not approve.
        await repo.write_audit(
            _audit(
                tenant_id=tenant_id,
                workspace_id=approval.workspace_id,
                actor_type="service",
                actor_id=None,
                action="social.approval_conflict",
                message_id=approval.message_id,
                after={
                    "approval_id": approval.approval_id,
                    "expected_status": "draft_ready",
                    "attempted_status": "approved",
                },
            )
        )
        return ApprovalResult("already_decided", approval.message_id)

    # Mark only the version this approval id names. A stale card must never
    # stamp a newer version the human did not see.
    latest = await repo.get_latest_version(tenant_id, approval.message_id)
    approved_version = _approval_version(approval.approval_id)
    if (
        latest is not None
        and approved_version is not None
        and latest.version == approved_version
    ):
        await repo.mark_version_approved(
            tenant_id, latest.id, decided_by, clock
        )
    else:
        await repo.write_audit(
            _audit(
                tenant_id=tenant_id,
                workspace_id=approval.workspace_id,
                actor_type="service",
                actor_id=None,
                action="social.approval_conflict",
                message_id=approval.message_id,
                after={
                    "approval_id": approval.approval_id,
                    "approved_version": approved_version,
                    "latest_version": (
                        latest.version if latest is not None else None
                    ),
                },
            )
        )
    await repo.write_audit(
        _audit(
            tenant_id=tenant_id,
            workspace_id=approval.workspace_id,
            actor_type="user",
            actor_id=decided_by,
            action="social.approved",
            message_id=approval.message_id,
            after={"approval_id": approval.approval_id},
        )
    )
    return ApprovalResult("approved", approval.message_id)


async def _reject(
    repo: GrowthRepository,
    *,
    tenant_id: UUID,
    approval: ApprovalRequest,
    decided_by: str,
) -> ApprovalResult:
    decided = await repo.decide_approval(
        tenant_id,
        approval.approval_id,
        "rejected",
        decided_by,
        reason="feishu_reject",
    )
    if not decided:
        return ApprovalResult("already_decided", approval.message_id)
    moved = await repo.update_message_status(
        tenant_id, approval.message_id, "draft_ready", "rejected"
    )
    if not moved:
        # The human decision stands; record that the message could not follow.
        await repo.write_audit(
            _audit(
                tenant_id=tenant_id,
                workspace_id=approval.workspace_id,
                actor_type="user",
                actor_id=decided_by,
                action="social.approval_conflict",
                message_id=approval.message_id,
                after={
                    "approval_id": approval.approval_id,
                    "expected_status": "draft_ready",
                    "status": "rejected",
                },
            )
        )
    await repo.write_audit(
        _audit(
            tenant_id=tenant_id,
            workspace_id=approval.workspace_id,
            actor_type="user",
            actor_id=decided_by,
            action="social.rejected",
            message_id=approval.message_id,
            after={"approval_id": approval.approval_id},
        )
    )
    return ApprovalResult("rejected", approval.message_id)


async def handle_approval(
    repo: GrowthRepository,
    *,
    tenant_id: UUID,
    action: FeishuAction,
    now: datetime | None = None,
) -> ApprovalResult:
    """Apply one Feishu action, never overwriting a decided approval."""
    clock = _clock(now)
    approval = await repo.get_approval_request(tenant_id, action.approval_id)
    if approval is None:
        return ApprovalResult("not_found")

    if approval.status != "pending":
        return ApprovalResult("already_decided", approval.message_id)

    decided_by = action.operator or "feishu"

    if action.action == "approve":
        return await _approve(
            repo,
            tenant_id=tenant_id,
            approval=approval,
            decided_by=decided_by,
            clock=clock,
        )
    if action.action == "reject":
        return await _reject(
            repo,
            tenant_id=tenant_id,
            approval=approval,
            decided_by=decided_by,
        )
    if action.action == "edit":
        return ApprovalResult("pending", approval.message_id, _EDIT_REASON)
    return ApprovalResult("pending", approval.message_id, _LATER_REASON)
