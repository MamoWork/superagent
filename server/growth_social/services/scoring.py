"""Server-side intent scoring for social leads.

The model only proposes per-dimension scores and penalty codes. Weights,
penalty points, thresholds, and the total score are owned by the server so a
prompt change or a misbehaving model cannot inflate a lead's score.
"""

from __future__ import annotations

import string
from datetime import datetime, timezone
from uuid import UUID

from growth_core.adapters.base import (
    LLMClient,
    ProviderBadOutput,
    ProviderNotConfigured,
)
from growth_core.repositories.base import GrowthRepository
from growth_core.schemas import NewTask, ScoringRubric
from growth_social.schemas import (
    IntentDimensionDraft,
    IntentPenaltyDraft,
    IntentScore,
    IntentScoreDraft,
)

__all__ = ["compute_intent_score", "score_lead"]

RUBRIC_KEY = "social_intent"
PROMPT_KEY = "social_intent"

_BAD_DIMENSIONS = "PROVIDER_BAD_OUTPUT: dimension ids do not match rubric"
_BAD_PENALTY = "PROVIDER_BAD_OUTPUT: unknown penalty code"
_MISSING_RUBRIC = "PROVIDER_NOT_CONFIGURED: social_intent rubric"
_MISSING_PROMPT = "PROVIDER_NOT_CONFIGURED: social_intent prompt"
_MISSING_LEAD = "LEAD_NOT_FOUND"

_SCORED_STATUSES = frozenset({"qualified", "watch", "dropped"})


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _age_days(published_at: datetime | None, now: datetime) -> str:
    if published_at is None:
        return ""
    return str(max(0, (_as_utc(now) - _as_utc(published_at)).days))


def _normalize_status(status: str) -> str:
    return status if status in _SCORED_STATUSES else "watch"


def compute_intent_score(
    dimensions: list[IntentDimensionDraft],
    penalties: list[IntentPenaltyDraft],
    rubric: ScoringRubric,
    *,
    summary: str = "",
) -> IntentScore:
    """Compute the authoritative score from validated model output.

    Each dimension contributes ``score * weight / 10``; each penalty
    contributes the rubric's points for its code (never the model's number),
    and repeated codes accumulate. The result is clamped to 0..100 and mapped
    onto the rubric's status thresholds.
    """
    weights = {d["id"]: d["weight"] for d in rubric.dimensions}
    rubric_points = {p["code"]: p["points"] for p in rubric.penalties}

    raw = sum(
        dimension.score * weights[dimension.dimension_id] / 10
        for dimension in dimensions
    )

    normalized_penalties: list[IntentPenaltyDraft] = []
    for penalty in penalties:
        points = rubric_points[penalty.code]
        raw += points
        normalized_penalties.append(penalty.model_copy(update={"points": points}))

    score = max(0, min(100, round(raw)))
    if score >= rubric.thresholds["qualified"]:
        status = "qualified"
    elif score >= rubric.thresholds["watch"]:
        status = "watch"
    else:
        status = "dropped"

    return IntentScore(
        score=score,
        status=status,
        dimensions=list(dimensions),
        penalties=normalized_penalties,
        summary=summary,
    )


def _render_user_prompt(
    template: str,
    *,
    platform: str,
    community: str,
    age_days: str,
    title: str,
    body: str,
) -> str:
    return string.Template(template).safe_substitute(
        platform=platform,
        community=community,
        age_days=age_days,
        title=title,
        body=body,
    )


def _validate_draft(
    draft: IntentScoreDraft, rubric: ScoringRubric
) -> None:
    expected_ids = sorted(dimension["id"] for dimension in rubric.dimensions)
    returned_ids = sorted(d.dimension_id for d in draft.dimensions)
    if returned_ids != expected_ids:
        raise ProviderBadOutput(_BAD_DIMENSIONS)

    rubric_codes = {penalty["code"] for penalty in rubric.penalties}
    if any(penalty.code not in rubric_codes for penalty in draft.penalties):
        raise ProviderBadOutput(_BAD_PENALTY)


async def score_lead(
    repo: GrowthRepository,
    llm: LLMClient,
    *,
    tenant_id: UUID,
    lead_id: UUID,
    model: str = "",
    now: datetime | None = None,
) -> IntentScore:
    """Score one lead, persist the result, and enqueue a draft when qualified.

    Already-scored leads short-circuit so a redelivered task never calls the
    LLM or duplicates a draft. If the lead status compare-and-set loses a race,
    the persisted row wins and no draft task is enqueued.
    """
    lead = await repo.get_lead(tenant_id, lead_id)
    if lead is None:
        raise LookupError(_MISSING_LEAD)

    if lead.score is not None:
        return IntentScore(
            score=lead.score,
            status=_normalize_status(lead.status),
            dimensions=[],
            penalties=[],
            summary="",
        )

    rubric = await repo.get_scoring_rubric(tenant_id, RUBRIC_KEY)
    if rubric is None:
        raise ProviderNotConfigured(_MISSING_RUBRIC)

    prompt = await repo.get_prompt_template(tenant_id, PROMPT_KEY)
    if prompt is None:
        raise ProviderNotConfigured(_MISSING_PROMPT)

    clock = datetime.now(timezone.utc) if now is None else now
    user = _render_user_prompt(
        prompt.user_template,
        platform=lead.platform,
        community=lead.subreddit or lead.platform,
        age_days=_age_days(lead.published_at, clock),
        title=lead.title,
        body=lead.body,
    )

    draft = await llm.complete_json(
        system=prompt.template,
        user=user,
        schema=IntentScoreDraft,
        model=model or None,
    )
    _validate_draft(draft, rubric)

    intent = compute_intent_score(
        draft.dimensions, draft.penalties, rubric, summary=draft.summary
    )

    updated = await repo.update_lead_status(
        lead.tenant_id,
        lead.id,
        lead.status,
        intent.status,
        score=intent.score,
        score_reasons=intent.model_dump(),
        model=model or getattr(llm, "model", None) or None,
        prompt_version=str(prompt.version),
    )

    if not updated:
        current = await repo.get_lead(tenant_id, lead_id)
        if current is not None and current.score is not None:
            return IntentScore(
                score=current.score,
                status=_normalize_status(current.status),
                dimensions=[],
                penalties=[],
                summary="",
            )
        return intent

    if intent.status == "qualified":
        await repo.enqueue_task(
            NewTask(
                tenant_id=lead.tenant_id,
                workspace_id=lead.workspace_id,
                pipeline="social",
                task_type="social.draft",
                payload={"lead_id": str(lead_id)},
                idempotency_key=f"draft:{lead_id}",
            )
        )

    return intent
