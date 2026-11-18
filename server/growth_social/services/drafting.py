"""Reply drafting and Feishu approval hand-off.

Drafting is the highest-risk step in the pipeline: it calls the model, renders
a link, enforces the link policy, and creates the message, version, approval,
and card outbox row. Every write is keyed by ``draft:{lead_id}`` or a
deterministic approval id so a worker retry after a partial failure cannot
create a second message, version, approval, or card.

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
from growth_core.schemas import (
    ApprovalRequest,
    NewApprovalRequest,
    NewAuditEntry,
    NewOutboxMessage,
    NewOutreachMessage,
    NewOutreachVersion,
    OutreachMessage,
    OutreachVersion,
    SocialLead,
)
from growth_social.schemas import IntentScore, ReplyDraft
from growth_social.services.cards import build_approval_card
from growth_social.services.link_policy import (
    LinkPolicyConfig,
    build_utm_url,
    validate_link_policy,
)
from growth_social.services.prompts import render_user_prompt

__all__ = ["draft_reply"]

PROMPT_KEY = "social_reply"

_LINK_PLACEHOLDER = "{{LINK}}"
_SCORED_STATUSES = frozenset({"qualified", "watch", "dropped"})
# Only pre-send states may need a repair card. ``sent`` is terminal: its card
# already went out, so re-drafting must not manufacture a fresh approval.
_REPAIRABLE_STATUSES = frozenset({"draft_ready", "approved"})

_MISSING_LEAD = "LEAD_NOT_FOUND"
_MISSING_PROMPT = "PROVIDER_NOT_CONFIGURED: social_reply prompt"
_PLACEHOLDER_COUNT = "PLACEHOLDER_COUNT"


def _clock(now: datetime | None) -> datetime:
    return datetime.now(timezone.utc) if now is None else now


def _require_setting(value: str, name: str) -> None:
    if not value:
        raise ProviderNotConfigured(f"PROVIDER_NOT_CONFIGURED: {name}")


def _subreddit_allows_links(lead: SocialLead) -> bool:
    """Link allowance follows the configured rule's truthiness.

    A missing key defaults to allowed; ``None``, ``0``, ``""`` and ``False``
    all mean links are not allowed for this subreddit.
    """
    return bool(lead.subreddit_rules.get("self_promotion_allowed", True))


def _card_score(lead: SocialLead) -> IntentScore:
    status = lead.status if lead.status in _SCORED_STATUSES else "watch"
    return IntentScore(
        score=lead.score or 0,
        status=status,
        dimensions=[],
        penalties=[],
        summary="",
    )


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


async def _record_policy_outcome(
    repo: GrowthRepository,
    *,
    tenant_id: UUID,
    workspace_id: UUID,
    lead: SocialLead,
    status: str,
    violations: list[str],
    action: str,
) -> OutreachMessage:
    """Persist a rejected or suppressed draft and its audit entry."""
    message = await repo.create_message(
        NewOutreachMessage(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            channel="social",
            provider=lead.platform,
            lead_id=lead.id,
            status=status,
            dedupe_key=f"draft:{lead.id}",
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


async def _ensure_approval_and_enqueue_card(
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

    Both writes are keyed by ``approval_id`` so retries and concurrent workers
    converge on one approval and one ``feishu:{approval_id}`` outbox row. The
    card is always rebuilt from ``version.body_text``, which is the immutable
    text that was validated at draft time.
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
        subreddit_allows_links=_subreddit_allows_links(lead),
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
    await _ensure_approval_and_enqueue_card(
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

    if draft.body_markdown.count(_LINK_PLACEHOLDER) != 1:
        return await _record_policy_outcome(
            repo,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            lead=lead,
            status="rejected",
            violations=[_PLACEHOLDER_COUNT],
            action="social.draft_rejected",
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
        subreddit_allows_links=_subreddit_allows_links(lead),
    )
    if policy.manual_only:
        return await _record_policy_outcome(
            repo,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            lead=lead,
            status="suppressed",
            violations=policy.violations,
            action="social.draft_suppressed",
        )
    if not policy.ok:
        return await _record_policy_outcome(
            repo,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            lead=lead,
            status="rejected",
            violations=policy.violations,
            action="social.draft_rejected",
        )

    message = await repo.create_message(
        NewOutreachMessage(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            channel="social",
            provider=lead.platform,
            lead_id=lead.id,
            status="draft_ready",
            dedupe_key=f"draft:{lead.id}",
            metadata={
                "subreddit": lead.subreddit,
                "has_link": True,
                "platform": lead.platform,
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
            model=(
                settings.llm_drafting_model
                or getattr(llm, "model", None)
                or None
            ),
            prompt_version=str(prompt.version),
            risk_flags=list(draft.risk_flags),
        )
        try:
            version = await repo.create_version(new_version)
        except Exception:
            # Broad catch by necessity: neither the in-memory fake nor the
            # Postgres repository exposes a shared unique-violation type here.
            # This protects the create-version crash window: another worker won
            # the ``(message, version=1)`` insert, so continue only if its row
            # is now visible.
            version = await repo.get_latest_version(tenant_id, message.id)
            if version is None:
                raise

    approval_id = f"{message.id}:v{version.version}"
    await _ensure_approval_and_enqueue_card(
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
    # The lead normally moves qualified -> draft_ready; a lost compare-and-set
    # means another worker already advanced it, which is fine.
    await _mark_lead_draft_ready(repo, tenant_id, lead)
    await repo.write_audit(
        _audit(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            action="social.draft_created",
            message_id=message.id,
            after={
                "approval_id": approval_id,
                "draft_version": version.version,
            },
        )
    )

    return message
