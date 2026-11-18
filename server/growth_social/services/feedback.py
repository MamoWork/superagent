"""Inbound social feedback: replies, negative signals, and unsubscribes.

This is the production write path for the outcomes that must stop the
pipeline. A reply marks the lead ``replied``; negative feedback, an
unsubscribe, or a moderator warning closes it as ``suppressed``. When the
author is public the service also suppresses that ``(platform, author)`` so a
future post from the same user is never auto-contacted.

Nothing is enqueued here. Pending sends and follow-ups are stopped by the
send gates in :mod:`growth_social.services.sending` and the lead-status checks
in :mod:`growth_social.services.followup`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from growth_core.repositories.base import GrowthRepository
from growth_core.schemas import NewAuditEntry, SocialLead

__all__ = [
    "FeedbackKind",
    "FeedbackLeadNotFound",
    "FeedbackResult",
    "record_feedback",
]

FeedbackKind = Literal["replied", "negative", "unsubscribe", "moderator_warning"]

_REPLIED = "replied"
_SUPPRESSED = "suppressed"
_USER_SOURCES = frozenset({"user", "manual", "operator", "human"})


class FeedbackLeadNotFound(Exception):
    """The requested lead does not exist in this tenant."""


@dataclass(frozen=True)
class FeedbackResult:
    lead_id: UUID
    status: str
    suppressed: bool


def _target_status(kind: FeedbackKind) -> str:
    return _REPLIED if kind == "replied" else _SUPPRESSED


def _actor_type(source: str) -> Literal["user", "integration"]:
    return "user" if source.strip().lower() in _USER_SOURCES else "integration"


async def _suppress_author(
    repo: GrowthRepository,
    *,
    tenant_id: UUID,
    lead: SocialLead,
    kind: FeedbackKind,
    source: str,
) -> None:
    if not lead.author_public:
        return
    await repo.add_suppression(
        tenant_id,
        "platform_user",
        f"{lead.platform}:{lead.author_public}",
        kind,
        source=source,
    )


async def record_feedback(
    repo: GrowthRepository,
    *,
    tenant_id: UUID,
    lead_id: UUID,
    kind: FeedbackKind,
    evidence: str = "",
    source: str = "api",
) -> FeedbackResult:
    """Apply one feedback event idempotently and audit it.

    A lost compare-and-set means a concurrent writer won; reload and return
    that state without duplicating the audit. Repeated identical calls are
    harmless: the target status is already in place, and suppression inserts
    are keyed ``(tenant_id, kind, value)``.
    """
    lead = await repo.get_lead(tenant_id, lead_id)
    if lead is None:
        raise FeedbackLeadNotFound(str(lead_id))

    target = _target_status(kind)
    if lead.status == target:
        await _suppress_author(
            repo, tenant_id=tenant_id, lead=lead, kind=kind, source=source
        )
        return FeedbackResult(lead.id, lead.status, lead.status == _SUPPRESSED)

    moved = await repo.update_lead_status(
        tenant_id,
        lead_id,
        expected_status=lead.status,
        status=target,
    )
    if not moved:
        current = await repo.get_lead(tenant_id, lead_id)
        if current is None:
            raise FeedbackLeadNotFound(str(lead_id))
        return FeedbackResult(
            current.id, current.status, current.status == _SUPPRESSED
        )

    await _suppress_author(
        repo, tenant_id=tenant_id, lead=lead, kind=kind, source=source
    )
    await repo.write_audit(
        NewAuditEntry(
            tenant_id=tenant_id,
            workspace_id=lead.workspace_id,
            actor_type=_actor_type(source),
            actor_id=source,
            action="social.feedback",
            entity_type="social_lead",
            entity_id=lead_id,
            after={
                "kind": kind,
                "evidence": evidence,
                "status": target,
                "suppressed": target == _SUPPRESSED,
            },
        )
    )
    return FeedbackResult(lead.id, target, target == _SUPPRESSED)
