"""Inbound social feedback: replies, negative signals, and unsubscribes.

This is the production write path for the outcomes that must stop the
pipeline. A reply marks the lead ``replied``; negative feedback, an
unsubscribe, or a moderator warning closes it as ``suppressed``. For the
closing kinds, a real public author is also added to the
``(platform, author)`` suppression list so a future post from the same user is
never auto-contacted. ``converted`` is terminal and is never downgraded.

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
from growth_social.services.author import is_contactable_author

__all__ = [
    "FeedbackKind",
    "FeedbackLeadNotFound",
    "FeedbackResult",
    "record_feedback",
]

FeedbackKind = Literal["replied", "negative", "unsubscribe", "moderator_warning"]

_REPLIED = "replied"
_SUPPRESSED = "suppressed"
_CONVERTED = "converted"
_USER_SOURCES = frozenset({"user", "manual", "operator", "human"})
_MAX_CAS_ATTEMPTS = 3

#: ``suppression_list.reason`` has its own database CHECK; feedback kinds do
#: not map one-to-one. ``replied`` is deliberately absent: a reply changes the
#: lead status but does not suppress the author.
_SUPPRESSION_REASON: dict[FeedbackKind, str | None] = {
    "replied": None,
    "negative": "negative_reply",
    "unsubscribe": "unsubscribe",
    "moderator_warning": "moderator_warning",
}


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
    reason = _SUPPRESSION_REASON[kind]
    if reason is None or not is_contactable_author(lead.author_public):
        return
    await repo.add_suppression(
        tenant_id,
        "platform_user",
        f"{lead.platform}:{lead.author_public}",
        reason,
        source=source,
    )


async def _audit_feedback(
    repo: GrowthRepository,
    *,
    tenant_id: UUID,
    lead: SocialLead,
    lead_id: UUID,
    kind: FeedbackKind,
    evidence: str,
    source: str,
    status: str,
) -> None:
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
                "status": status,
                "suppressed": status == _SUPPRESSED,
            },
        )
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
    """Apply one feedback event and always audit the genuine call.

    A lost compare-and-set means a concurrent writer won; the lead is reloaded
    and the transition retried (bounded). ``converted`` is terminal and is
    never downgraded, but the feedback is still recorded in the audit trail.
    Repeated calls are harmless and intentionally audit again: suppression
    inserts are keyed ``(tenant_id, kind, value)`` and the result stays stable.
    """
    lead = await repo.get_lead(tenant_id, lead_id)
    if lead is None:
        raise FeedbackLeadNotFound(str(lead_id))

    target = _target_status(kind)
    attempts = 0
    while True:
        # ``converted`` is terminal; a late reply must not reopen or close it.
        if lead.status == _CONVERTED or lead.status == target:
            await _suppress_author(
                repo, tenant_id=tenant_id, lead=lead, kind=kind, source=source
            )
            await _audit_feedback(
                repo,
                tenant_id=tenant_id,
                lead=lead,
                lead_id=lead_id,
                kind=kind,
                evidence=evidence,
                source=source,
                status=lead.status,
            )
            return FeedbackResult(
                lead.id, lead.status, lead.status == _SUPPRESSED
            )

        if attempts >= _MAX_CAS_ATTEMPTS:
            break

        moved = await repo.update_lead_status(
            tenant_id,
            lead_id,
            expected_status=lead.status,
            status=target,
        )
        attempts += 1
        if moved:
            await _suppress_author(
                repo, tenant_id=tenant_id, lead=lead, kind=kind, source=source
            )
            await _audit_feedback(
                repo,
                tenant_id=tenant_id,
                lead=lead,
                lead_id=lead_id,
                kind=kind,
                evidence=evidence,
                source=source,
                status=target,
            )
            return FeedbackResult(lead.id, target, target == _SUPPRESSED)

        current = await repo.get_lead(tenant_id, lead_id)
        if current is None:
            raise FeedbackLeadNotFound(str(lead_id))
        lead = current

    # Every CAS attempt lost to concurrent writers. The event is still real,
    # so record it against the state that finally won.
    await _suppress_author(
        repo, tenant_id=tenant_id, lead=lead, kind=kind, source=source
    )
    await _audit_feedback(
        repo,
        tenant_id=tenant_id,
        lead=lead,
        lead_id=lead_id,
        kind=kind,
        evidence=evidence,
        source=source,
        status=lead.status,
    )
    return FeedbackResult(lead.id, lead.status, lead.status == _SUPPRESSED)
