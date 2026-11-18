"""Bounded, enqueue-only social follow-up generation.

A follow-up check is the asynchronous tail of a manual send: Task 19 records
that a human posted the first reply and queues one check a day later. This
module decides what that check does.

Follow-ups are capped (``followup_max_total``), spaced (at least
``followup_min_interval_hours`` between sends), and stop entirely once the lead
has replied, converted, been suppressed, or rejected. Every check is
idempotent: the retry task and the draft are both keyed deterministically, so a
worker crash between any two writes never produces a second follow-up or a
duplicate approval card.

Nothing here posts, comments, or DMs. A drafted follow-up only enqueues a
``feishu.card`` outbox row; delivery belongs to
:func:`growth_core.services.outbox.dispatch_outbox`.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from growth_core.adapters.base import LLMClient, Notifier, ProviderNotConfigured
from growth_core.config import GrowthSettings
from growth_core.repositories.base import GrowthRepository
from growth_core.schemas import (
    NewAuditEntry,
    NewOutreachMessage,
    NewOutreachVersion,
    NewTask,
    OutreachMessage,
    SocialLead,
)
from growth_social.schemas import ReplyDraft
from growth_social.services.approval import (
    ensure_approval_and_enqueue_card,
    subreddit_allows_links,
)
from growth_social.services.link_policy import (
    LinkPolicyConfig,
    build_utm_url,
    validate_link_policy,
)
from growth_social.services.prompts import render_user_prompt

__all__ = ["FollowUpDecision", "process_followup_check"]

PROMPT_KEY = "social_followup"

_LINK_PLACEHOLDER = "{{LINK}}"
#: Follow-ups are pointless once the lead has replied or been closed.
_CLOSED_LEAD_STATUSES = frozenset(
    {"replied", "converted", "suppressed", "rejected"}
)
#: Only pre-send states need an approval-card repair on retry. ``sent`` is
#: terminal: its card already went out and must not be re-manufactured.
_REPAIRABLE_STATUSES = frozenset({"draft_ready", "approved"})

_MISSING_PROMPT = "PROVIDER_NOT_CONFIGURED: social_followup prompt"
_PLACEHOLDER_COUNT = "PLACEHOLDER_COUNT"


class FollowUpDecision:
    """String outcomes of a follow-up check (enum-like constants)."""

    CREATED = "created"
    RESCHEDULED = "rescheduled"
    STOPPED = "stopped"


def _clock(now: datetime | None) -> datetime:
    return datetime.now(timezone.utc) if now is None else now


def _require_setting(value: str, name: str) -> None:
    if not value:
        raise ProviderNotConfigured(f"PROVIDER_NOT_CONFIGURED: {name}")


def _audit(
    *,
    tenant_id: UUID,
    workspace_id: UUID,
    action: str,
    message_id: UUID,
    after: dict | None = None,
) -> NewAuditEntry:
    return NewAuditEntry(
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        actor_type="service",
        action=action,
        entity_type="outreach_message",
        entity_id=message_id,
        after=after,
    )


def _dedupe_key(original_message_id: UUID, index: int) -> str:
    return f"followup:{original_message_id}:{index}"


def _new_followup_message(
    *,
    tenant_id: UUID,
    workspace_id: UUID,
    lead: SocialLead,
    original_message_id: UUID,
    index: int,
    status: str,
    metadata: dict,
) -> NewOutreachMessage:
    return NewOutreachMessage(
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        channel="social",
        provider=lead.platform,
        lead_id=lead.id,
        status=status,
        dedupe_key=_dedupe_key(original_message_id, index),
        metadata=metadata,
    )


async def _record_policy_outcome(
    repo: GrowthRepository,
    *,
    tenant_id: UUID,
    workspace_id: UUID,
    lead: SocialLead,
    original_message_id: UUID,
    index: int,
    status: str,
    violations: list[str],
    action: str,
) -> OutreachMessage:
    """Persist a rejected or suppressed follow-up and its audit entry.

    The dedupe key matches the one a successful draft would use, so a retry
    finds this row instead of drafting again.
    """
    message = await repo.create_message(
        _new_followup_message(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            lead=lead,
            original_message_id=original_message_id,
            index=index,
            status=status,
            metadata={"policy_violations": list(violations)},
        )
    )
    await repo.write_audit(
        _audit(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            action=action,
            message_id=message.id,
            after={"policy_violations": list(violations)},
        )
    )
    return message


async def _resume_existing(
    repo: GrowthRepository,
    *,
    tenant_id: UUID,
    workspace_id: UUID,
    existing: OutreachMessage,
    lead: SocialLead,
    settings: GrowthSettings,
    clock: datetime,
) -> OutreachMessage:
    """Return an existing follow-up, repairing its approval/card if needed."""
    latest = await repo.get_latest_version(tenant_id, existing.id)
    if latest is None or existing.status not in _REPAIRABLE_STATUSES:
        return existing

    await ensure_approval_and_enqueue_card(
        repo,
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        message=existing,
        approval_id=f"{existing.id}:v{latest.version}",
        lead=lead,
        version=latest,
        settings=settings,
        clock=clock,
    )
    return existing


async def process_followup_check(
    repo: GrowthRepository,
    llm: LLMClient,
    notifier: Notifier | None,
    *,
    tenant_id: UUID,
    workspace_id: UUID,
    original_message_id: UUID,
    settings: GrowthSettings,
    now: datetime | None = None,
) -> OutreachMessage | None:
    """Process one ``social.followup_check`` task.

    ``notifier`` is accepted for the worker handler but is never used here:
    card delivery is performed by
    :func:`growth_core.services.outbox.dispatch_outbox`.

    Returns the created (or existing) follow-up message, or ``None`` when the
    check stopped or was rescheduled.
    """
    clock = _clock(now)

    original = await repo.get_message(tenant_id, original_message_id)
    if original is None or original.status != "sent":
        return None

    lead: SocialLead | None = None
    if original.lead_id is not None:
        lead = await repo.get_lead(tenant_id, original.lead_id)
    if lead is None:
        return None
    if lead.status in _CLOSED_LEAD_STATUSES:
        return None
    if lead.author_public:
        suppressed = await repo.is_suppressed(
            tenant_id,
            "platform_user",
            f"{lead.platform}:{lead.author_public}",
        )
        if suppressed:
            return None

    count = await repo.count_followups(tenant_id, original_message_id)
    if count >= settings.followup_max_total:
        return None

    interval = timedelta(hours=settings.followup_min_interval_hours)
    last = await repo.latest_sent_at(tenant_id, lead.id)
    if last is not None and clock - last < interval:
        await repo.enqueue_task(
            NewTask(
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                pipeline="social",
                task_type="social.followup_check",
                payload={"original_message_id": str(original_message_id)},
                idempotency_key=(
                    f"followup:{original_message_id}:retry:"
                    f"{int(clock.timestamp())}"
                ),
                run_after=last + interval,
            )
        )
        return None

    index = count + 1
    existing = await repo.find_message_by_dedupe_key(
        tenant_id, _dedupe_key(original_message_id, index)
    )
    if existing is not None:
        return await _resume_existing(
            repo,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            existing=existing,
            lead=lead,
            settings=settings,
            clock=clock,
        )

    _require_setting(settings.product_url, "product_url")
    _require_setting(settings.product_domain, "product_domain")
    _require_setting(settings.feishu_chat_id, "feishu_chat_id")

    prompt = await repo.get_prompt_template(tenant_id, PROMPT_KEY)
    if prompt is None:
        raise ProviderNotConfigured(_MISSING_PROMPT)

    previous = await repo.get_latest_version(tenant_id, original_message_id)
    previous_text = previous.body_text if previous is not None else ""

    user = render_user_prompt(
        prompt.user_template,
        title=lead.title or "",
        body=lead.body or "",
        previous_reply=previous_text,
        followup_index=str(index),
        product_name=settings.product_name or settings.product_domain,
    )
    draft = await llm.complete_json(
        system=prompt.template,
        user=user,
        schema=ReplyDraft,
        model=settings.llm_drafting_model or None,
    )

    if draft.body_markdown.count(_LINK_PLACEHOLDER) != 1:
        return await _record_policy_outcome(
            repo,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            lead=lead,
            original_message_id=original_message_id,
            index=index,
            status="rejected",
            violations=[_PLACEHOLDER_COUNT],
            action="social.followup_rejected",
        )

    url = build_utm_url(
        settings.product_url,
        draft.link_path,
        lead_id=str(lead.id),
        platform=lead.platform,
    )
    final_text = draft.body_markdown.replace(_LINK_PLACEHOLDER, url)

    policy = validate_link_policy(
        final_text,
        LinkPolicyConfig(allowed_domain=settings.product_domain),
        subreddit_allows_links=subreddit_allows_links(lead),
    )
    if policy.manual_only:
        return await _record_policy_outcome(
            repo,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            lead=lead,
            original_message_id=original_message_id,
            index=index,
            status="suppressed",
            violations=policy.violations,
            action="social.followup_suppressed",
        )
    if not policy.ok:
        return await _record_policy_outcome(
            repo,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            lead=lead,
            original_message_id=original_message_id,
            index=index,
            status="rejected",
            violations=policy.violations,
            action="social.followup_rejected",
        )

    message = await repo.create_message(
        _new_followup_message(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            lead=lead,
            original_message_id=original_message_id,
            index=index,
            status="draft_ready",
            metadata={
                "followup_of": str(original_message_id),
                "followup_index": index,
                "subreddit": lead.subreddit,
                "has_link": True,
                "draft_version": 1,
            },
        )
    )

    version = await repo.get_latest_version(tenant_id, message.id)
    if version is None:
        new_version = NewOutreachVersion(
            tenant_id=tenant_id,
            message_id=message.id,
            version=1,
            body_text=final_text,
            cta_url=url,
            model=getattr(llm, "model", None) or None,
            prompt_version=str(prompt.version),
            risk_flags=list(draft.risk_flags),
        )
        try:
            version = await repo.create_version(new_version)
        except Exception:
            # Neither the fake nor the Postgres repository exposes a shared
            # unique-violation type. If another worker won the
            # ``(message, version=1)`` insert, continue only when its row is
            # now visible.
            version = await repo.get_latest_version(tenant_id, message.id)
            if version is None:
                raise

    approval_id = f"{message.id}:v1"
    await ensure_approval_and_enqueue_card(
        repo,
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        message=message,
        approval_id=approval_id,
        lead=lead,
        version=version,
        settings=settings,
        clock=clock,
    )
    await repo.write_audit(
        _audit(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            action="social.followup_created",
            message_id=message.id,
            after={
                "original_message_id": str(original_message_id),
                "followup_index": index,
            },
        )
    )

    updated = await repo.get_message(tenant_id, message.id)
    return updated or message
