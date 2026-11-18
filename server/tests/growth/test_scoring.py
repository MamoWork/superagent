"""Tests for the server-side intent scoring service."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest

from growth_core import seed_data
from growth_core.adapters.base import (
    ProviderBadOutput,
    ProviderNotConfigured,
    ProviderUnavailable,
)
from growth_core.schemas import PromptTemplate, ScoringRubric, SocialLead
from growth_social.schemas import (
    IntentDimensionDraft,
    IntentPenaltyDraft,
    IntentScoreDraft,
)
from growth_social.services.scoring import score_lead
from tests.growth.fakes import FakeGrowthRepository


class FakeLLM:
    """Deterministic LLM double that records every call."""

    model = "fake-model"

    def __init__(self, draft: IntentScoreDraft | None = None, *, exc=None) -> None:
        self.draft = draft
        self.exc = exc
        self.calls: list[dict] = []

    async def complete_json(self, *, system, user, schema, model=None):
        self.calls.append(
            {"system": system, "user": user, "schema": schema, "model": model}
        )
        if self.exc is not None:
            raise self.exc
        assert self.draft is not None
        return self.draft


class RaceRepo(FakeGrowthRepository):
    """Repository whose update always loses a compare-and-set race.

    ``get_lead`` returns the replacement row from the second read onwards,
    which is exactly the row another worker would have written.
    """

    def __init__(self, replacement: SocialLead | None) -> None:
        super().__init__()
        self.replacement = replacement
        self.reads = 0

    async def get_lead(self, tenant_id: UUID, lead_id: UUID):
        self.reads += 1
        if self.reads > 1:
            return self.replacement
        return await super().get_lead(tenant_id, lead_id)

    async def update_lead_status(self, *args, **kwargs) -> bool:
        return False


def _rubric(tenant_id: UUID, **overrides) -> ScoringRubric:
    data = {
        "id": uuid4(),
        "tenant_id": tenant_id,
        "key": seed_data.SCORING_RUBRIC_KEY,
        "version": seed_data.SCORING_RUBRIC_VERSION,
        "dimensions": [dict(d) for d in seed_data.SCORING_RUBRIC_DIMENSIONS],
        "penalties": [dict(p) for p in seed_data.SCORING_RUBRIC_PENALTIES],
        "thresholds": dict(seed_data.SCORING_RUBRIC_THRESHOLDS),
        "enabled": True,
    }
    data.update(overrides)
    return ScoringRubric(**data)


def _prompt(tenant_id: UUID, **overrides) -> PromptTemplate:
    data = {
        "id": uuid4(),
        "tenant_id": tenant_id,
        "key": seed_data.SCORING_RUBRIC_KEY,
        "module": "social",
        "version": seed_data.SCORING_RUBRIC_VERSION,
        "template": seed_data.SOCIAL_INTENT_SYSTEM,
        "user_template": seed_data.SOCIAL_INTENT_USER,
        "output_schema": {"type": "object"},
        "enabled": True,
    }
    data.update(overrides)
    return PromptTemplate(**data)


def _seed_config(repo, tenant_id: UUID) -> None:
    repo.rubrics[(tenant_id, "social_intent", 1)] = _rubric(tenant_id)
    repo.prompts[(tenant_id, "social_intent", 1)] = _prompt(tenant_id)


def _make_lead(
    tenant_id: UUID,
    workspace_id: UUID,
    *,
    platform: str = "reddit",
    subreddit: str | None = "SaaS",
    title: str = "How do you keep onboarding emails personal?",
    body: str = "Our welcome sequence feels generic after 200 signups.",
    published_at: datetime | None = None,
    status: str = "new",
    score: int | None = None,
) -> SocialLead:
    clock = datetime(2026, 11, 15, 9, 0, tzinfo=timezone.utc)
    return SocialLead(
        id=uuid4(),
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        platform=platform,
        platform_post_id=str(uuid4()),
        title=title,
        body=body,
        source_url="https://example.test/post",
        published_at=published_at,
        subreddit=subreddit,
        dedupe_key=str(uuid4()),
        status=status,
        score=score,
        created_at=clock,
        updated_at=clock,
    )


def _add_lead(repo, tenant_id: UUID, workspace_id: UUID, **kwargs) -> SocialLead:
    lead = _make_lead(tenant_id, workspace_id, **kwargs)
    repo.leads.append(lead.model_copy(deep=True))
    return lead


def _draft(
    scores: dict[str, int] | None = None,
    penalties: list[IntentPenaltyDraft] | None = None,
    summary: str = "Looks like a real fit.",
) -> IntentScoreDraft:
    if scores is None:
        scores = {d["id"]: 10 for d in seed_data.SCORING_RUBRIC_DIMENSIONS}
    return IntentScoreDraft(
        dimensions=[
            IntentDimensionDraft(
                dimension_id=dimension_id, score=score, rationale=f"{dimension_id} ok"
            )
            for dimension_id, score in scores.items()
        ],
        penalties=list(penalties or []),
        summary=summary,
    )


def _rubric_dimensions() -> dict[str, int]:
    return {d["id"]: 10 for d in seed_data.SCORING_RUBRIC_DIMENSIONS}


# ---------------------------------------------------------------------------
# Configuration and lead precondition failures
# ---------------------------------------------------------------------------


async def test_missing_rubric_is_provider_not_configured(repo, now):
    tenant, workspace = uuid4(), uuid4()
    repo.prompts[(tenant, "social_intent", 1)] = _prompt(tenant)
    lead = _add_lead(repo, tenant, workspace)
    llm = FakeLLM(_draft())

    with pytest.raises(ProviderNotConfigured) as excinfo:
        await score_lead(repo, llm, tenant_id=tenant, lead_id=lead.id, now=now)

    assert str(excinfo.value) == "PROVIDER_NOT_CONFIGURED: social_intent rubric"
    assert llm.calls == []


async def test_missing_prompt_is_provider_not_configured(repo, now):
    tenant, workspace = uuid4(), uuid4()
    repo.rubrics[(tenant, "social_intent", 1)] = _rubric(tenant)
    lead = _add_lead(repo, tenant, workspace)
    llm = FakeLLM(_draft())

    with pytest.raises(ProviderNotConfigured) as excinfo:
        await score_lead(repo, llm, tenant_id=tenant, lead_id=lead.id, now=now)

    assert str(excinfo.value) == "PROVIDER_NOT_CONFIGURED: social_intent prompt"
    assert llm.calls == []


# ---------------------------------------------------------------------------
# Prompt rendering
# ---------------------------------------------------------------------------


async def test_renders_prompt_exactly(repo, now):
    tenant, workspace = uuid4(), uuid4()
    _seed_config(repo, tenant)
    lead = _add_lead(
        repo,
        tenant,
        workspace,
        platform="reddit",
        subreddit="SaaS",
        title="Need a better onboarding checklist",
        body="Our sequence feels generic.",
        published_at=now - timedelta(days=3),
    )
    llm = FakeLLM(_draft())

    await score_lead(repo, llm, tenant_id=tenant, lead_id=lead.id, now=now)

    assert len(llm.calls) == 1
    call = llm.calls[0]
    assert call["system"] == seed_data.SOCIAL_INTENT_SYSTEM
    assert call["user"] == (
        "Platform: reddit\n"
        "Community: SaaS\n"
        "Post age (days): 3\n"
        "Title: Need a better onboarding checklist\n"
        "Body:\n"
        "Our sequence feels generic.\n"
    )
    assert call["schema"] is IntentScoreDraft
    assert call["model"] is None


async def test_community_falls_back_to_platform_and_age_variants(repo, now):
    tenant, workspace = uuid4(), uuid4()
    _seed_config(repo, tenant)
    cases = [
        ("none", None, ""),
        ("old", now - timedelta(days=200), "200"),
        ("future", now + timedelta(days=5), "0"),
    ]
    leads = []
    for label, published_at, _ in cases:
        leads.append(
            _add_lead(
                repo,
                tenant,
                workspace,
                platform="hackernews",
                subreddit=None,
                title=f"post {label}",
                body=f"body {label}",
                published_at=published_at,
            )
        )
    llm = FakeLLM(_draft())

    for lead in leads:
        await score_lead(repo, llm, tenant_id=tenant, lead_id=lead.id, now=now)

    assert len(llm.calls) == 3
    for call, (label, _, expected_age) in zip(llm.calls, cases, strict=True):
        assert call["user"] == (
            "Platform: hackernews\n"
            "Community: hackernews\n"
            f"Post age (days): {expected_age}\n"
            f"Title: post {label}\n"
            "Body:\n"
            f"body {label}\n"
        )


async def test_explicit_model_is_forwarded(repo, now):
    tenant, workspace = uuid4(), uuid4()
    _seed_config(repo, tenant)
    lead = _add_lead(repo, tenant, workspace)
    llm = FakeLLM(_draft())

    await score_lead(
        repo, llm, tenant_id=tenant, lead_id=lead.id, model="cheap-model", now=now
    )

    assert llm.calls[0]["model"] == "cheap-model"


# ---------------------------------------------------------------------------
# Output validation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "scores",
    [
        # missing reply_safety
        {
            "real_help": 10,
            "pain_specificity": 10,
            "buyer_role": 10,
            "product_fit": 10,
        },
        # extra id
        {**_rubric_dimensions(), "vibes": 10},
    ],
    ids=["missing", "extra"],
)
async def test_dimension_set_must_match_rubric(repo, now, scores):
    tenant, workspace = uuid4(), uuid4()
    _seed_config(repo, tenant)
    lead = _add_lead(repo, tenant, workspace)
    llm = FakeLLM(_draft(scores))

    with pytest.raises(ProviderBadOutput) as excinfo:
        await score_lead(repo, llm, tenant_id=tenant, lead_id=lead.id, now=now)

    assert str(excinfo.value) == (
        "PROVIDER_BAD_OUTPUT: dimension ids do not match rubric"
    )
    stored = await repo.get_lead(tenant, lead.id)
    assert stored is not None
    assert stored.score is None
    assert stored.status == "new"
    assert repo.tasks_for(f"draft:{lead.id}") == []


async def test_duplicate_dimension_id_is_bad_output(repo, now):
    tenant, workspace = uuid4(), uuid4()
    _seed_config(repo, tenant)
    lead = _add_lead(repo, tenant, workspace)
    llm = FakeLLM(
        IntentScoreDraft(
            dimensions=[
                IntentDimensionDraft(dimension_id="real_help", score=10),
                IntentDimensionDraft(dimension_id="real_help", score=10),
                IntentDimensionDraft(dimension_id="pain_specificity", score=10),
                IntentDimensionDraft(dimension_id="buyer_role", score=10),
                IntentDimensionDraft(dimension_id="product_fit", score=10),
            ]
        )
    )

    with pytest.raises(ProviderBadOutput) as excinfo:
        await score_lead(repo, llm, tenant_id=tenant, lead_id=lead.id, now=now)

    assert str(excinfo.value) == (
        "PROVIDER_BAD_OUTPUT: dimension ids do not match rubric"
    )


async def test_unknown_penalty_code_is_bad_output(repo, now):
    tenant, workspace = uuid4(), uuid4()
    _seed_config(repo, tenant)
    lead = _add_lead(repo, tenant, workspace)
    llm = FakeLLM(
        _draft(
            penalties=[IntentPenaltyDraft(code="mystery", points=-10)],
        )
    )

    with pytest.raises(ProviderBadOutput) as excinfo:
        await score_lead(repo, llm, tenant_id=tenant, lead_id=lead.id, now=now)

    assert str(excinfo.value) == "PROVIDER_BAD_OUTPUT: unknown penalty code"
    stored = await repo.get_lead(tenant, lead.id)
    assert stored is not None and stored.score is None


# ---------------------------------------------------------------------------
# Server-authoritative scorecard
# ---------------------------------------------------------------------------


async def test_penalty_points_are_server_authoritative(repo, now):
    tenant, workspace = uuid4(), uuid4()
    _seed_config(repo, tenant)
    lead = _add_lead(repo, tenant, workspace)
    llm = FakeLLM(
        _draft(penalties=[IntentPenaltyDraft(code="ad", points=0, rationale="ad")])
    )

    result = await score_lead(repo, llm, tenant_id=tenant, lead_id=lead.id, now=now)

    assert result.score == 50
    assert result.status == "dropped"
    assert result.penalties[0].points == -50
    stored = await repo.get_lead(tenant, lead.id)
    assert stored is not None
    assert stored.score_reasons is not None
    assert stored.score_reasons["penalties"][0]["points"] == -50


async def test_repeated_penalty_codes_accumulate(repo, now):
    tenant, workspace = uuid4(), uuid4()
    _seed_config(repo, tenant)
    lead = _add_lead(repo, tenant, workspace)
    llm = FakeLLM(
        _draft(
            penalties=[
                IntentPenaltyDraft(code="already_solved", points=0),
                IntentPenaltyDraft(code="already_solved", points=0),
            ]
        )
    )

    result = await score_lead(repo, llm, tenant_id=tenant, lead_id=lead.id, now=now)

    assert result.score == 60
    assert result.status == "watch"
    assert [p.points for p in result.penalties] == [-20, -20]


async def test_score_is_clamped_to_range(repo, now):
    tenant, workspace = uuid4(), uuid4()
    _seed_config(repo, tenant)
    low_lead = _add_lead(repo, tenant, workspace)
    high_lead = _add_lead(repo, tenant, workspace)
    low_llm = FakeLLM(
        _draft(
            scores={d["id"]: 0 for d in seed_data.SCORING_RUBRIC_DIMENSIONS},
            penalties=[IntentPenaltyDraft(code="competitor_or_bait", points=0)],
        )
    )
    high_llm = FakeLLM(_draft())

    low = await score_lead(
        repo, low_llm, tenant_id=tenant, lead_id=low_lead.id, now=now
    )
    high = await score_lead(
        repo, high_llm, tenant_id=tenant, lead_id=high_lead.id, now=now
    )

    assert low.score == 0
    assert low.status == "dropped"
    assert high.score == 100
    assert high.status == "qualified"


# ---------------------------------------------------------------------------
# Status thresholds and task enqueueing
# ---------------------------------------------------------------------------


async def test_watch_and_dropped_do_not_enqueue(repo, now):
    tenant, workspace = uuid4(), uuid4()
    _seed_config(repo, tenant)
    watch_lead = _add_lead(repo, tenant, workspace)
    dropped_lead = _add_lead(repo, tenant, workspace)
    watch_llm = FakeLLM(
        _draft(scores={d["id"]: 7 for d in seed_data.SCORING_RUBRIC_DIMENSIONS})
    )
    dropped_llm = FakeLLM(
        _draft(scores={d["id"]: 5 for d in seed_data.SCORING_RUBRIC_DIMENSIONS})
    )

    watch = await score_lead(
        repo, watch_llm, tenant_id=tenant, lead_id=watch_lead.id, now=now
    )
    dropped = await score_lead(
        repo, dropped_llm, tenant_id=tenant, lead_id=dropped_lead.id, now=now
    )

    assert (watch.score, watch.status) == (70, "watch")
    assert (dropped.score, dropped.status) == (50, "dropped")
    assert repo.tasks == []


async def test_qualified_enqueues_exact_draft_task(repo, now):
    tenant, workspace = uuid4(), uuid4()
    _seed_config(repo, tenant)
    lead = _add_lead(repo, tenant, workspace)
    llm = FakeLLM(_draft())

    result = await score_lead(repo, llm, tenant_id=tenant, lead_id=lead.id, now=now)

    assert result.score == 100
    assert result.status == "qualified"
    tasks = repo.tasks_for(f"draft:{lead.id}")
    assert len(tasks) == 1
    task = tasks[0]
    assert task.tenant_id == lead.tenant_id
    assert task.workspace_id == lead.workspace_id
    assert task.pipeline == "social"
    assert task.task_type == "social.draft"
    assert task.payload == {"lead_id": str(lead.id)}
    assert task.idempotency_key == f"draft:{lead.id}"

    # A second scoring pass sees the persisted score and does not duplicate work.
    second = await score_lead(repo, llm, tenant_id=tenant, lead_id=lead.id, now=now)
    assert second.score == 100
    assert len(repo.tasks_for(f"draft:{lead.id}")) == 1
    assert len(llm.calls) == 1


# ---------------------------------------------------------------------------
# Idempotent short-circuit and concurrency
# ---------------------------------------------------------------------------


async def test_already_scored_lead_short_circuits(repo, now):
    tenant, workspace = uuid4(), uuid4()
    _seed_config(repo, tenant)
    lead = _add_lead(repo, tenant, workspace, status="qualified", score=77)
    llm = FakeLLM(exc=AssertionError("LLM must not be called"))

    result = await score_lead(repo, llm, tenant_id=tenant, lead_id=lead.id, now=now)

    assert result.score == 77
    assert result.status == "qualified"
    assert result.dimensions == []
    assert result.penalties == []
    assert result.summary == ""
    assert llm.calls == []
    # A qualified lead always has a draft task (re-enqueued idempotently).
    tasks = repo.tasks_for(f"draft:{lead.id}")
    assert len(tasks) == 1
    assert tasks[0].task_type == "social.draft"


async def test_rescoring_qualified_lead_reenqueues_draft_idempotently(repo, now):
    tenant, workspace = uuid4(), uuid4()
    _seed_config(repo, tenant)
    lead = _add_lead(repo, tenant, workspace, status="qualified", score=81)
    llm = FakeLLM(exc=AssertionError("LLM must not be called"))

    await score_lead(repo, llm, tenant_id=tenant, lead_id=lead.id, now=now)
    await score_lead(repo, llm, tenant_id=tenant, lead_id=lead.id, now=now)

    tasks = repo.tasks_for(f"draft:{lead.id}")
    assert len(tasks) == 1
    assert tasks[0].idempotency_key == f"draft:{lead.id}"
    assert llm.calls == []


async def test_already_scored_lead_normalizes_unknown_status(repo, now):
    tenant, workspace = uuid4(), uuid4()
    _seed_config(repo, tenant)
    lead = _add_lead(repo, tenant, workspace, status="contacted", score=55)
    llm = FakeLLM(exc=AssertionError("LLM must not be called"))

    result = await score_lead(repo, llm, tenant_id=tenant, lead_id=lead.id, now=now)

    assert (result.score, result.status) == (55, "watch")


async def test_lost_update_returns_persisted_score_without_enqueueing(repo, now):
    tenant, workspace = uuid4(), uuid4()
    original = _make_lead(tenant, workspace)
    replacement = original.model_copy(update={"score": 88, "status": "contacted"})
    race = RaceRepo(replacement)
    _seed_config(race, tenant)
    race.leads.append(original.model_copy(deep=True))
    llm = FakeLLM(_draft())

    result = await score_lead(race, llm, tenant_id=tenant, lead_id=original.id, now=now)

    assert (result.score, result.status) == (88, "watch")
    assert result.dimensions == []
    assert result.penalties == []
    assert race.reads == 2
    assert race.tasks == []


async def test_lost_update_with_unscored_reread_returns_computed_score(repo, now):
    tenant, workspace = uuid4(), uuid4()
    original = _make_lead(tenant, workspace)
    replacement = original.model_copy(update={"score": None})
    race = RaceRepo(replacement)
    _seed_config(race, tenant)
    race.leads.append(original.model_copy(deep=True))
    llm = FakeLLM(_draft())

    computed = await score_lead(
        race, llm, tenant_id=tenant, lead_id=original.id, now=now
    )

    assert (computed.score, computed.status) == (100, "qualified")
    assert len(computed.dimensions) == 5
    assert race.reads == 2
    assert race.tasks == []


# ---------------------------------------------------------------------------
# Persisted audit fields
# ---------------------------------------------------------------------------


async def test_explicit_model_argument_is_recorded(repo, now):
    tenant, workspace = uuid4(), uuid4()
    _seed_config(repo, tenant)
    lead = _add_lead(repo, tenant, workspace)
    llm = FakeLLM(_draft())

    await score_lead(
        repo, llm, tenant_id=tenant, lead_id=lead.id, model="scoring-model", now=now
    )

    stored = await repo.get_lead(tenant, lead.id)
    assert stored is not None
    assert stored.model == "scoring-model"
    assert stored.prompt_version == "1"
    assert stored.score_reasons is not None
    assert stored.score_reasons["score"] == 100
    assert stored.score_reasons["status"] == "qualified"
    assert stored.score_reasons["summary"] == "Looks like a real fit."


async def test_llm_model_is_recorded_when_argument_is_omitted(repo, now):
    tenant, workspace = uuid4(), uuid4()
    _seed_config(repo, tenant)
    lead = _add_lead(repo, tenant, workspace)
    llm = FakeLLM(_draft())
    assert llm.model == "fake-model"

    await score_lead(repo, llm, tenant_id=tenant, lead_id=lead.id, now=now)

    stored = await repo.get_lead(tenant, lead.id)
    assert stored is not None
    assert stored.model == "fake-model"


async def test_llm_without_model_attribute_records_none(repo, now):
    tenant, workspace = uuid4(), uuid4()
    _seed_config(repo, tenant)
    lead = _add_lead(repo, tenant, workspace)
    llm = FakeLLM(_draft())
    llm.model = None

    await score_lead(repo, llm, tenant_id=tenant, lead_id=lead.id, now=now)

    stored = await repo.get_lead(tenant, lead.id)
    assert stored is not None
    assert stored.model is None


async def test_llm_failure_leaves_lead_unchanged(repo, now):
    tenant, workspace = uuid4(), uuid4()
    _seed_config(repo, tenant)
    lead = _add_lead(repo, tenant, workspace, status="discovered")
    llm = FakeLLM(
        exc=ProviderUnavailable("PROVIDER_UNAVAILABLE: llm timeout")
    )

    with pytest.raises(ProviderUnavailable):
        await score_lead(repo, llm, tenant_id=tenant, lead_id=lead.id, now=now)

    stored = await repo.get_lead(tenant, lead.id)
    assert stored is not None
    assert stored.score is None
    assert stored.status == "discovered"
    assert repo.tasks == []


# ---------------------------------------------------------------------------
# Error messages never leak post content
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "draft",
    [
        _draft(penalties=[IntentPenaltyDraft(code="mystery", points=-10)]),
        _draft(
            scores={
                "real_help": 10,
                "pain_specificity": 10,
                "buyer_role": 10,
                "product_fit": 10,
            }
        ),
    ],
    ids=["unknown-penalty", "dimension-mismatch"],
)
async def test_errors_never_contain_post_content(repo, now, draft):
    tenant, workspace = uuid4(), uuid4()
    _seed_config(repo, tenant)
    lead = _add_lead(
        repo,
        tenant,
        workspace,
        title="SECRET_TITLE_MARKER",
        body="SECRET_BODY_MARKER",
    )
    llm = FakeLLM(draft)

    with pytest.raises(ProviderBadOutput) as excinfo:
        await score_lead(repo, llm, tenant_id=tenant, lead_id=lead.id, now=now)

    message = str(excinfo.value)
    assert "SECRET_TITLE_MARKER" not in message
    assert "SECRET_BODY_MARKER" not in message
