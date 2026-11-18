"""Shared draft construction for first replies and follow-ups.

Both :mod:`growth_social.services.drafting` and
:mod:`growth_social.services.followup` render exactly one official link,
enforce the same link policy, and create the same message/version/approval/card
shape. Keeping that pipeline in one place means the security-critical rules
(single ``{{LINK}}``, UTM parameters, disclosure, allowed domain, no
shorteners) cannot drift between the two callers.

This module performs no LLM calls and never delivers anything: the Feishu card
is only enqueued by :func:`ensure_approval_and_enqueue_card`, and delivery
belongs to :func:`growth_core.services.outbox.dispatch_outbox`.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from growth_core.config import GrowthSettings
from growth_core.repositories.base import GrowthRepository
from growth_core.schemas import (
    NewAuditEntry,
    NewOutreachMessage,
    NewOutreachVersion,
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
    LinkPolicyResult,
    build_utm_url,
    validate_link_policy,
)

__all__ = [
    "LINK_PLACEHOLDER",
    "PLACEHOLDER_COUNT",
    "RenderedDraft",
    "create_draft_with_approval",
    "record_policy_outcome",
    "render_reply_link",
]

LINK_PLACEHOLDER = "{{LINK}}"
PLACEHOLDER_COUNT = "PLACEHOLDER_COUNT"

ExistingHandler = Callable[[OutreachMessage], Awaitable[OutreachMessage]]


@dataclass(frozen=True)
class RenderedDraft:
    """A model draft after link rendering and policy validation."""

    final_text: str
    url: str | None
    policy: LinkPolicyResult
    placeholder_count: int


def _audit(
    *,
    tenant_id: UUID,
    workspace_id: UUID,
    action: str,
    message_id: UUID,
    after: dict[str, Any] | None = None,
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


def render_reply_link(
    draft: ReplyDraft,
    *,
    lead: SocialLead,
    settings: GrowthSettings,
) -> RenderedDraft:
    """Render the single official link and validate the final text.

    A draft must contain exactly one ``{{LINK}}`` placeholder. Anything else is
    a policy failure recorded as ``PLACEHOLDER_COUNT`` without attempting to
    build a URL. Otherwise the placeholder is replaced with the UTM link and
    the full link policy runs against the final text.
    """
    count = draft.body_markdown.count(LINK_PLACEHOLDER)
    if count != 1:
        return RenderedDraft(
            final_text=draft.body_markdown,
            url=None,
            policy=LinkPolicyResult(
                ok=False, link_url=None, violations=[PLACEHOLDER_COUNT]
            ),
            placeholder_count=count,
        )

    url = build_utm_url(
        settings.product_url,
        draft.link_path,
        lead_id=str(lead.id),
        platform=lead.platform,
    )
    final_text = draft.body_markdown.replace(LINK_PLACEHOLDER, url)
    policy = validate_link_policy(
        final_text,
        LinkPolicyConfig(allowed_domain=settings.product_domain),
        subreddit_allows_links=subreddit_allows_links(lead),
    )
    return RenderedDraft(
        final_text=final_text,
        url=url,
        policy=policy,
        placeholder_count=count,
    )


async def record_policy_outcome(
    repo: GrowthRepository,
    *,
    tenant_id: UUID,
    workspace_id: UUID,
    lead: SocialLead,
    dedupe_key: str,
    violations: list[str],
    suppressed: bool,
    audit_action: str,
    clock: datetime,
    metadata_extra: dict[str, Any] | None = None,
) -> OutreachMessage:
    """Persist a rejected or suppressed draft and its audit entry.

    ``clock`` is accepted so both callers pass one timeline even though no
    timestamp is written here. ``metadata_extra`` lets a caller attach its own
    keys while the policy violations always win under ``policy_violations``.
    """
    metadata: dict[str, Any] = {"policy_violations": list(violations)}
    if metadata_extra:
        metadata.update(metadata_extra)

    message = await repo.create_message(
        NewOutreachMessage(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            channel="social",
            provider=lead.platform,
            lead_id=lead.id,
            status="suppressed" if suppressed else "rejected",
            dedupe_key=dedupe_key,
            metadata=metadata,
        )
    )
    await repo.write_audit(
        _audit(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            action=audit_action,
            message_id=message.id,
            after={"policy_violations": list(violations)},
        )
    )
    return message


async def create_draft_with_approval(
    repo: GrowthRepository,
    *,
    tenant_id: UUID,
    workspace_id: UUID,
    lead: SocialLead,
    settings: GrowthSettings,
    dedupe_key: str,
    version_number: int,
    final_text: str,
    url: str | None,
    model: str | None,
    prompt_version: str | None,
    risk_flags: list[str],
    metadata: dict[str, Any],
    audit_action: str,
    clock: datetime,
    mark_lead_draft_ready: bool,
    audit_after: dict[str, Any] | None = None,
    on_existing: ExistingHandler | None = None,
) -> OutreachMessage:
    """Create the draft message, its version, approval, and card outbox row.

    Every write is keyed so a worker retry cannot create a second message,
    version, approval, or card. ``on_existing`` is an optional repair hook: if
    ``create_message`` returns a row another worker already versioned (a
    ``ON CONFLICT DO NOTHING`` race), the caller can take over instead of
    attaching a fresh approval.

    ``audit_after`` defaults to the approval/version payload used by drafting;
    callers with a different payload pass it explicitly.
    """
    message = await repo.create_message(
        NewOutreachMessage(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            channel="social",
            provider=lead.platform,
            lead_id=lead.id,
            status="draft_ready",
            dedupe_key=dedupe_key,
            metadata=metadata,
        )
    )

    version = await repo.get_latest_version(tenant_id, message.id)
    if version is not None and on_existing is not None:
        # Another worker created and versioned this row between our lookup and
        # our insert; let the caller resume it rather than duplicating.
        return await on_existing(message)

    if version is None:
        new_version = NewOutreachVersion(
            tenant_id=tenant_id,
            message_id=message.id,
            version=version_number,
            body_text=final_text,
            cta_url=url,
            model=model,
            prompt_version=prompt_version,
            risk_flags=list(risk_flags),
        )
        try:
            version = await repo.create_version(new_version)
        except Exception:
            # Neither the in-memory fake nor the Postgres repository exposes a
            # shared unique-violation type here. This protects the
            # create-version crash window: another worker won the
            # ``(message, version)`` insert, so continue only if its row is now
            # visible.
            version = await repo.get_latest_version(tenant_id, message.id)
            if version is None:
                raise

    approval_id = f"{message.id}:v{version.version}"
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
    if mark_lead_draft_ready:
        # Best-effort compare-and-set: a lost race is harmless because another
        # worker already advanced the lead.
        await repo.update_lead_status(
            tenant_id, lead.id, lead.status, "draft_ready"
        )
    if audit_after is None:
        audit_after = {
            "approval_id": approval_id,
            "draft_version": version.version,
        }
    await repo.write_audit(
        _audit(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            action=audit_action,
            message_id=message.id,
            after=audit_after,
        )
    )

    updated = await repo.get_message(tenant_id, message.id)
    return updated or message
