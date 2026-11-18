"""Golden-set regression tests for the intent scoring prompt and scorecard.

The deterministic test scores the stored per-post dimensions with the same
server-side scorecard used in production, so it needs no network access. The
live test is opt-in through ``GROWTH_TEST_LLM_API_KEY`` and exercises the real
prompt against an OpenAI-compatible endpoint.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest

from growth_core import seed_data
from growth_core.adapters.llm import OpenAICompatibleLLM
from growth_core.schemas import PromptTemplate, ScoringRubric, SocialLead
from growth_social.schemas import IntentDimensionDraft, IntentPenaltyDraft
from growth_social.services.scoring import compute_intent_score, score_lead
from tests.growth.fakes import FakeGrowthRepository

GOLDEN_PATH = Path(__file__).parent / "golden" / "social_posts.jsonl"
QUALIFIED = "qualified"
PRECISION_FLOOR = 0.8


def load_rows() -> list[dict]:
    lines = [line for line in GOLDEN_PATH.read_text(encoding="utf-8").splitlines() if line]
    return [json.loads(line) for line in lines]


def seed_rubric(tenant_id) -> ScoringRubric:
    return ScoringRubric(
        id=uuid4(),
        tenant_id=tenant_id,
        key=seed_data.SCORING_RUBRIC_KEY,
        version=seed_data.SCORING_RUBRIC_VERSION,
        dimensions=[dict(d) for d in seed_data.SCORING_RUBRIC_DIMENSIONS],
        penalties=[dict(p) for p in seed_data.SCORING_RUBRIC_PENALTIES],
        thresholds=dict(seed_data.SCORING_RUBRIC_THRESHOLDS),
        enabled=True,
    )


def seed_prompt(tenant_id) -> PromptTemplate:
    return PromptTemplate(
        id=uuid4(),
        tenant_id=tenant_id,
        key=seed_data.SCORING_RUBRIC_KEY,
        module=seed_data.PROMPT_MODULE,
        version=seed_data.PROMPT_VERSION,
        template=seed_data.SOCIAL_INTENT_SYSTEM,
        user_template=seed_data.SOCIAL_INTENT_USER,
        output_schema=dict(seed_data.PROMPT_OUTPUT_SCHEMA),
        enabled=True,
    )


def precision_qualified(pairs: list[tuple[str, str]]) -> float:
    """Fraction of rows predicted qualified that are labeled qualified."""
    predicted = [expected for expected, computed in pairs if computed == QUALIFIED]
    if not predicted:
        return 0.0
    return sum(1 for expected in predicted if expected == QUALIFIED) / len(predicted)


def test_golden_set_is_well_formed():
    rows = load_rows()
    assert len(rows) == 50
    assert len({row["id"] for row in rows}) == 50

    statuses = [row["expected_status"] for row in rows]
    assert statuses.count("qualified") == 25
    assert len(statuses) - statuses.count("qualified") == 25

    assert {row["platform"] for row in rows} == {"reddit", "hackernews"}

    rubric_ids = {d["id"] for d in seed_data.SCORING_RUBRIC_DIMENSIONS}
    rubric_codes = {p["code"] for p in seed_data.SCORING_RUBRIC_PENALTIES}
    for row in rows:
        dimension_ids = [d["dimension_id"] for d in row["dimensions"]]
        assert sorted(dimension_ids) == sorted(rubric_ids)
        assert all(0 <= d["score"] <= 10 for d in row["dimensions"])
        assert all(p["code"] in rubric_codes for p in row["penalties"])
        assert isinstance(row["age_days"], int)

    penalty_codes = {p["code"] for row in rows for p in row["penalties"]}
    assert {"ad", "already_solved", "stale_90d", "duplicate"} <= penalty_codes

    stale_rows = [row for row in rows if row["age_days"] > 90]
    assert stale_rows
    assert all(
        any(p["code"] == "stale_90d" for p in row["penalties"]) for row in stale_rows
    )


def test_golden_set_precision_at_threshold():
    rows = load_rows()
    tenant_id = uuid4()
    rubric = seed_rubric(tenant_id)
    pairs: list[tuple[str, str]] = []

    for row in rows:
        dimensions = [IntentDimensionDraft(**d) for d in row["dimensions"]]
        penalties = [IntentPenaltyDraft(**p) for p in row["penalties"]]
        intent = compute_intent_score(dimensions, penalties, rubric)
        assert intent.status == row["expected_status"], row["id"]
        pairs.append((row["expected_status"], intent.status))

    assert precision_qualified(pairs) >= PRECISION_FLOOR


@pytest.mark.skipif(
    not (os.getenv("GROWTH_TEST_LLM") or os.getenv("GROWTH_TEST_LLM_API_KEY")),
    reason="GROWTH_TEST_LLM or GROWTH_TEST_LLM_API_KEY is not set; live prompt regression is opt-in",
)
async def test_live_golden_set_precision():
    rows = load_rows()
    tenant_id = uuid4()
    workspace_id = uuid4()
    now = datetime.now(timezone.utc)

    llm = OpenAICompatibleLLM(
        api_key=os.getenv("GROWTH_TEST_LLM_API_KEY") or os.getenv("GROWTH_TEST_LLM") or "",
        model=os.environ.get("GROWTH_TEST_LLM_MODEL", "gpt-4o-mini"),
        base_url=os.environ.get("GROWTH_TEST_LLM_BASE_URL"),
    )
    repo = FakeGrowthRepository()
    repo.rubrics[(tenant_id, seed_data.SCORING_RUBRIC_KEY, 1)] = seed_rubric(tenant_id)
    repo.prompts[(tenant_id, seed_data.SCORING_RUBRIC_KEY, 1)] = seed_prompt(tenant_id)

    leads: list[tuple[SocialLead, dict]] = []
    for row in rows:
        lead = SocialLead(
            id=uuid4(),
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            platform=row["platform"],
            platform_post_id=row["id"],
            title=row["title"],
            body=row["body"],
            source_url=f"https://example.test/{row['id']}",
            published_at=now - timedelta(days=row["age_days"]),
            dedupe_key=row["id"],
            status="new",
            created_at=now,
            updated_at=now,
        )
        repo.leads.append(lead.model_copy(deep=True))
        leads.append((lead, row))

    pairs: list[tuple[str, str]] = []
    try:
        for lead, row in leads:
            result = await score_lead(
                repo,
                llm,
                tenant_id=tenant_id,
                lead_id=lead.id,
                model=os.environ.get("GROWTH_TEST_LLM_MODEL", "gpt-4o-mini"),
                now=now,
            )
            pairs.append((row["expected_status"], result.status))
    finally:
        await llm.aclose()

    assert precision_qualified(pairs) >= PRECISION_FLOOR
