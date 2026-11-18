"""Reply drafting and Feishu approval hand-off.

Drafting is the highest-risk step in the pipeline: it calls the model, renders
a link, enforces the link policy, and creates the message, version, approval,
and card outbox row. Every write is keyed by ``draft:{lead_id}`` or a
deterministic approval id so a worker retry after a partial failure cannot
create a second message, version, approval, or card.

The link rendering, policy recording, and draft creation pipeline is shared
with follow-up drafting in :mod:`growth_social.services.draft_flow`, so the
security-critical rules cannot drift between the two.

Drafting is enqueue-only: it builds the ``feishu.card`` row and leaves
delivery to :func:`growth_core.services.outbox.dispatch_outbox`, which the
worker loop owns. A retry re-enqueues the same ``feishu:{approval_id}`` row
(idempotently), so an already-pending or already-sent card is never duplicated.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from growth_core.adapters.base import LLMClient, Notifier, ProviderNotConfigured
from growth_core.config import GrowthSettings
from growth_core.repositories.base import GrowthRepository
from growth_core.schemas import OutreachMessage, SocialLead
from growth_social.schemas import ReplyDraft
from growth_social.services.approval import ensure_approval_and_enqueue_card
from growth_social.services.draft_flow import (
    PLACEHOLDER_COUNT,
    create_draft_with_approval,
    record_policy_outcome,
    render_reply_link,
)
from growth_social.services.prompts import render_user_prompt

__all__ = ["draft_reply"]

PROMPT_KEY = "social_reply"

# Only pre-send states may need a repair card. ``sent`` is terminal: its card
# already went out, so re-drafting must not manufacture a fresh approval.
_REPAIRABLE_STATUSES = frozenset({"draft_ready", "approved"})

_MISSING_LEAD = "LEAD_NOT_FOUND"
_MISSING_PROMPT = "PROVIDER_NOT_CONFIGURED: social_reply prompt"


def _clock(now: datetime | None) -> datetime:
    return datetime.now(timezone.utc) if now is None else now


def _require_setting(value: str, name: str) -> None:
    if not value:
        raise ProviderNotConfigured(f"PROVIDER_NOT_CONFIGURED: {name}")


async def _mark_lead_draft_ready(
    repo: GrowthRepository, tenant_id: UUID, lead: SocialLead
) -> None:
    """Best-effort compare-and-set move; a lost race is harmless."""
    await repo.update_lead_status(
        tenant_id, lead.id, lead.status, "draft_ready"
    )


async def _resume_existing(
    repo: GrowthRepository,
    *,
    tenant_id: UUID,
    workspace_id: UUID,
    lead_id: UUID,
    existing: OutreachMessage,
    settings: GrowthSettings,
    clock: datetime,
) -> OutreachMessage:
    """Return an existing draft, repairing approval/card state if needed."""
    if existing.status not in _REPAIRABLE_STATUSES:
        return existing

    latest = await repo.get_latest_version(tenant_id, existing.id)
    if latest is None:
        # Known crash window: message committed, version not yet. Returning the
        # row untouched lets the next worker retry start from a clean state
        # rather than manufacturing a version it cannot validate.
        return existing

    resolved_lead_id = existing.lead_id or lead_id
    lead = await repo.get_lead(tenant_id, resolved_lead_id)
    if lead is None:
        raise LookupError(_MISSING_LEAD)

    approval_id = f"{existing.id}:v{latest.version}"
    await ensure_approval_and_enqueue_card(
        repo,
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        message=existing,
        approval_id=approval_id,
        lead=lead,
        version=latest,
        settings=settings,
        clock=clock,
    )
    await _mark_lead_draft_ready(repo, tenant_id, lead)
    return existing


async def draft_reply(
    repo: GrowthRepository,
    llm: LLMClient,
    notifier: Notifier | None,
    *,
    tenant_id: UUID,
    workspace_id: UUID,
    lead_id: UUID,
    settings: GrowthSettings,
    now: datetime | None = None,
) -> OutreachMessage:
    """Draft one reply for a lead and enqueue its Feishu approval card.

    ``notifier`` is accepted for the worker handler but is not used here:
    delivery is performed by
    :func:`growth_core.services.outbox.dispatch_outbox`.
    """
    clock = _clock(now)

    existing = await repo.find_message_by_dedupe_key(
        tenant_id, f"draft:{lead_id}"
    )
    if existing is not None:
        return await _resume_existing(
            repo,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            lead_id=lead_id,
            existing=existing,
            settings=settings,
            clock=clock,
        )

    lead = await repo.get_lead(tenant_id, lead_id)
    if lead is None:
        raise LookupError(_MISSING_LEAD)

    _require_setting(settings.product_url, "product_url")
    _require_setting(settings.product_domain, "product_domain")
    _require_setting(settings.feishu_chat_id, "feishu_chat_id")

    prompt = await repo.get_prompt_template(tenant_id, PROMPT_KEY)
    if prompt is None:
        raise ProviderNotConfigured(_MISSING_PROMPT)

    user = render_user_prompt(
        prompt.user_template,
        platform=lead.platform,
        community=lead.subreddit or lead.platform,
        title=lead.title,
        body=lead.body,
        product_name=settings.product_name or settings.product_domain,
        product_url=settings.product_url,
    )
    draft = await llm.complete_json(
        system=prompt.template,
        user=user,
        schema=ReplyDraft,
        model=settings.llm_drafting_model or None,
    )

    rendered = render_reply_link(draft, lead=lead, settings=settings)
    if rendered.placeholder_count != 1:
        return await record_policy_outcome(
            repo,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            lead=lead,
            dedupe_key=f"draft:{lead.id}",
            violations=[PLACEHOLDER_COUNT],
            suppressed=False,
            audit_action="social.draft_rejected",
            clock=clock,
        )
    if rendered.policy.manual_only:
        return await record_policy_outcome(
            repo,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            lead=lead,
            dedupe_key=f"draft:{lead.id}",
            violations=rendered.policy.violations,
            suppressed=True,
            audit_action="social.draft_suppressed",
            clock=clock,
        )
    if not rendered.policy.ok:
        return await record_policy_outcome(
            repo,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            lead=lead,
            dedupe_key=f"draft:{lead.id}",
            violations=rendered.policy.violations,
            suppressed=False,
            audit_action="social.draft_rejected",
            clock=clock,
        )

    return await create_draft_with_approval(
        repo,
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        lead=lead,
        settings=settings,
        dedupe_key=f"draft:{lead.id}",
        version_number=1,
        final_text=rendered.final_text,
        url=rendered.url,
        model=(
            settings.llm_drafting_model
            or getattr(llm, "model", None)
            or None
        ),
        prompt_version=str(prompt.version),
        risk_flags=list(draft.risk_flags),
        metadata={
            "subreddit": lead.subreddit,
            "has_link": True,
            "platform": lead.platform,
            "draft_version": 1,
        },
        audit_action="social.draft_created",
        clock=clock,
        mark_lead_draft_ready=True,
    )
