"""Record that a human posted a reply, and enforce send-time limits.

Nothing here sends anything: the operator posts manually, then calls
:func:`mark_sent`. This module only moves database state, records the delivery,
writes an audit trail, and schedules the follow-up check.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from growth_core.repositories.base import GrowthRepository
from growth_core.schemas import (
    NewAuditEntry,
    NewDeliveryLog,
    NewTask,
    OutreachMessage,
)
from growth_core.services.ratelimit import RateLimitContext, check_send_allowed
from growth_social.services.author import is_contactable_author

__all__ = ["SendBlocked", "mark_sent"]

#: Original messages may not follow a lead who has already been contacted.
#: These map to ``ALREADY_CONTACTED``.
_CONTACTED_STATUSES = frozenset({"sent", "replied", "converted"})
#: A closed lead may not receive an original message; these map to
#: ``LEAD_CLOSED`` (the contacted statuses above take precedence).
_ORIGINAL_CLOSED_STATUSES = frozenset({"suppressed", "rejected"})
#: Follow-ups are pointless once the lead has replied or been closed.
_CLOSED_STATUSES = frozenset({"replied", "converted", "suppressed", "rejected"})


class SendBlocked(Exception):
    """A human-recorded send cannot be applied to this message.

    ``str(exc)`` is always ``code`` so callers can match on the stable code.
    """

    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        self.detail = detail or code
        super().__init__(code)

    def __str__(self) -> str:
        return self.code


def _audit(
    *,
    tenant_id: UUID,
    workspace_id: UUID,
    actor_type: str,
    actor_id: str | None,
    action: str,
    message_id: UUID,
    after: dict[str, object] | None = None,
) -> NewAuditEntry:
    return NewAuditEntry(
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        actor_type=actor_type,  # type: ignore[arg-type]
        actor_id=actor_id,
        action=action,
        entity_type="outreach_message",
        entity_id=message_id,
        after=after,
    )


async def mark_sent(
    repo: GrowthRepository,
    *,
    tenant_id: UUID,
    workspace_id: UUID,
    message_id: UUID,
    sent_at: datetime | None = None,
    channel: str = "manual",
    operator: str | None = None,
    now: datetime | None = None,
) -> OutreachMessage:
    """Apply one human-recorded send and schedule the follow-up check.

    The transition is compare-and-set from ``approved``; an over-limit,
    suppressed, same-author, or closed-lead message is moved to ``suppressed``
    so it never stays approved.

    Block codes:

    * ``ALREADY_CONTACTED`` — the lead is ``sent``/``replied``/``converted``.
    * ``LEAD_CLOSED`` — the lead is ``suppressed``/``rejected`` (follow-ups
      treat every closed status the same way).
    * ``ALREADY_CONTACTED_USER`` — another original message in this tenant
      already reached the same ``(platform, author_public)``.
    """
    effective = now or sent_at or datetime.now(timezone.utc)

    message = await repo.get_message(tenant_id, message_id)
    if message is None:
        raise SendBlocked("NOT_FOUND", "message")
    if message.status != "approved":
        raise SendBlocked("INVALID_TRANSITION")

    lead = None
    if message.lead_id is not None:
        lead = await repo.get_lead(tenant_id, message.lead_id)
    if lead is None:
        raise SendBlocked("NOT_FOUND", "lead")

    meta = message.metadata or {}
    is_followup = "followup_of" in meta

    if not is_followup:
        if lead.status in _CONTACTED_STATUSES:
            raise SendBlocked("ALREADY_CONTACTED")
        if lead.status in _ORIGINAL_CLOSED_STATUSES:
            raise SendBlocked("LEAD_CLOSED")
    elif lead.status in _CLOSED_STATUSES:
        raise SendBlocked("LEAD_CLOSED")

    if is_contactable_author(lead.author_public):
        suppressed = await repo.is_suppressed(
            tenant_id,
            "platform_user",
            f"{lead.platform}:{lead.author_public}",
        )
        if suppressed:
            await repo.update_message_status(
                tenant_id,
                message_id,
                expected_status="approved",
                status="suppressed",
            )
            await repo.write_audit(
                _audit(
                    tenant_id=tenant_id,
                    workspace_id=workspace_id,
                    actor_type="service",
                    actor_id=operator,
                    action="social.send_suppressed",
                    message_id=message_id,
                    after={"reason": "platform_user"},
                )
            )
            raise SendBlocked("SUPPRESSED")

    if not is_followup and is_contactable_author(lead.author_public):
        already_contacted = await repo.has_contacted_author(
            tenant_id,
            lead.platform,
            lead.author_public,
            message_id,
        )
        if already_contacted:
            await repo.update_message_status(
                tenant_id,
                message_id,
                expected_status="approved",
                status="suppressed",
            )
            await repo.write_audit(
                _audit(
                    tenant_id=tenant_id,
                    workspace_id=workspace_id,
                    actor_type="service",
                    actor_id=operator,
                    action="social.send_blocked",
                    message_id=message_id,
                    after={
                        "scope": "author",
                        "platform": lead.platform,
                        "author_public": lead.author_public,
                    },
                )
            )
            raise SendBlocked("ALREADY_CONTACTED_USER")

    decision = await check_send_allowed(
        repo,
        RateLimitContext(
            tenant_id=tenant_id,
            channel="social",
            platform=lead.platform,
            subreddit=lead.subreddit,
            has_link=True,
            now=effective,
        ),
    )
    if not decision.allowed:
        scope = decision.exceeded_scope or "global"
        scope_key = decision.exceeded_scope_key or "*"
        await repo.update_message_status(
            tenant_id,
            message_id,
            expected_status="approved",
            status="suppressed",
        )
        await repo.write_audit(
            _audit(
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                actor_type="service",
                actor_id=operator,
                action="social.send_blocked",
                message_id=message_id,
                after={
                    "scope": scope,
                    "scope_key": scope_key,
                    "retry_after_seconds": decision.retry_after_seconds,
                },
            )
        )
        raise SendBlocked("RATE_LIMITED", f"{scope}:{scope_key}")

    latest = await repo.get_latest_version(tenant_id, message_id)
    moved = await repo.update_message_status(
        tenant_id,
        message_id,
        expected_status="approved",
        status="sent",
        sent_at=effective,
        provider=lead.platform,
        metadata_patch={
            "channel": channel,
            "subreddit": lead.subreddit,
            "has_link": True,
            "draft_version": latest.version if latest else 0,
        },
    )
    if not moved:
        # Surface the winner's state; this send lost the compare-and-set.
        await repo.get_message(tenant_id, message_id)
        raise SendBlocked("CONCURRENT_UPDATE")

    # The human already sent: a lost lead CAS must not undo the message.
    await repo.update_lead_status(
        tenant_id, lead.id, expected_status=lead.status, status="sent"
    )

    # A delayed Feishu tap must never re-approve a sent message.
    await repo.expire_pending_approvals(tenant_id, message_id)

    await repo.record_delivery(
        NewDeliveryLog(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            message_id=message_id,
            lead_id=lead.id,
            provider=lead.platform,
            event_type="sent",
            payload={"channel": channel},
        )
    )

    original_id = meta.get("followup_of", str(message.id))
    await repo.enqueue_task(
        NewTask(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            pipeline="social",
            task_type="social.followup_check",
            payload={"original_message_id": original_id},
            idempotency_key=f"followup:{original_id}:{message.id}",
            run_after=effective + timedelta(days=1),
        )
    )

    await repo.write_audit(
        _audit(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            actor_type="user",
            actor_id=operator,
            action="social.sent",
            message_id=message_id,
            after={"channel": channel},
        )
    )

    updated = await repo.get_message(tenant_id, message_id)
    return updated or message
