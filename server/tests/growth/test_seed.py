import json
import os
import uuid

import asyncpg
import pytest

from growth_core.migrate import apply_migrations
from growth_core.scripts.seed import seed_tenant

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not os.getenv("GROWTH_TEST_DATABASE_URL"),
        reason="GROWTH_TEST_DATABASE_URL is not set",
    ),
]

EXPECTED_DIMENSIONS = [
    {"id": "real_help", "weight": 30},
    {"id": "pain_specificity", "weight": 25},
    {"id": "buyer_role", "weight": 20},
    {"id": "product_fit", "weight": 15},
    {"id": "reply_safety", "weight": 10},
]
EXPECTED_PENALTIES = [
    {"code": "ad", "points": -50},
    {"code": "already_solved", "points": -20},
    {"code": "stale_90d", "points": -20},
    {"code": "duplicate", "points": -30},
    {"code": "competitor_or_bait", "points": -50},
]
EXPECTED_THRESHOLDS = {"qualified": 80, "watch": 60}
EXPECTED_PROVIDERS = {
    ("social_source", "reddit"),
    ("social_source", "hackernews"),
    ("notifier", "feishu"),
    ("llm", "openai_compatible"),
}
EXPECTED_RATE_RULES = {
    ("global", "*", 50),
    ("platform", "reddit", 5),
    ("subreddit", "*", 2),
}
EXPECTED_PROMPT_KEYS = {"social_intent", "social_reply", "social_followup"}


def _as_json(value):
    """asyncpg returns jsonb values as text; decode when needed."""
    return json.loads(value) if isinstance(value, str) else value


async def _group_counts(conn, tenant_id):
    tables = (
        "provider_configs",
        "scoring_rubrics",
        "tenant_quotas",
        "tenant_features",
        "rate_limit_rules",
        "prompt_templates",
    )
    return {
        table: await conn.fetchval(
            f"select count(*) from {table} where tenant_id = $1", tenant_id
        )
        for table in tables
    }


async def test_seed_is_idempotent_and_seeds_every_group():
    url = os.environ["GROWTH_TEST_DATABASE_URL"]
    await apply_migrations(url)
    tenant_id, workspace_id = uuid.uuid4(), uuid.uuid4()
    conn = await asyncpg.connect(url)
    try:
        await seed_tenant(conn, tenant_id=tenant_id, workspace_id=workspace_id)

        first_counts = await _group_counts(conn, tenant_id)
        assert first_counts == {
            "provider_configs": 4,
            "scoring_rubrics": 1,
            "tenant_quotas": 1,
            "tenant_features": 1,
            "rate_limit_rules": 3,
            "prompt_templates": 3,
        }

        # Second run must not raise and must not change any seeded group.
        await seed_tenant(conn, tenant_id=tenant_id, workspace_id=workspace_id)
        assert await _group_counts(conn, tenant_id) == first_counts

        assert await conn.fetchval(
            "select count(*) from tenants where id = $1", tenant_id
        ) == 1
        assert await conn.fetchval(
            "select count(*) from workspaces where id = $1 and tenant_id = $2",
            workspace_id,
            tenant_id,
        ) == 1

        provider_rows = await conn.fetch(
            "select capability, provider, secret_ref from provider_configs "
            "where tenant_id = $1",
            tenant_id,
        )
        assert {
            (row["capability"], row["provider"]) for row in provider_rows
        } == EXPECTED_PROVIDERS
        secret_refs = {
            (row["capability"], row["provider"]): row["secret_ref"]
            for row in provider_rows
        }
        assert secret_refs[("social_source", "reddit")] == "GROWTH_REDDIT_USER_AGENT"
        assert secret_refs[("social_source", "hackernews")] is None

        rubric = await conn.fetchrow(
            "select dimensions, penalties, thresholds from scoring_rubrics "
            "where tenant_id = $1 and key = 'social_intent' and version = 1",
            tenant_id,
        )
        assert rubric is not None
        assert _as_json(rubric["dimensions"]) == EXPECTED_DIMENSIONS
        assert _as_json(rubric["penalties"]) == EXPECTED_PENALTIES
        assert _as_json(rubric["thresholds"]) == EXPECTED_THRESHOLDS

        quota = await conn.fetchrow(
            "select limit_value, used_value from tenant_quotas "
            "where tenant_id = $1 and metric = 'social_replies' and period = 'day'",
            tenant_id,
        )
        assert quota is not None
        assert quota["limit_value"] == 50
        assert quota["used_value"] == 0

        feature_enabled = await conn.fetchval(
            "select enabled from tenant_features "
            "where tenant_id = $1 and feature_key = 'social_module'",
            tenant_id,
        )
        assert feature_enabled is True

        rate_rows = await conn.fetch(
            "select scope, scope_key, max_count, workspace_id "
            "from rate_limit_rules where tenant_id = $1",
            tenant_id,
        )
        assert {
            (row["scope"], row["scope_key"], row["max_count"])
            for row in rate_rows
        } == EXPECTED_RATE_RULES
        assert all(row["workspace_id"] is None for row in rate_rows)

        prompt_rows = await conn.fetch(
            "select key, module, version, template, user_template, "
            "output_schema, model_hint from prompt_templates where tenant_id = $1",
            tenant_id,
        )
        assert {row["key"] for row in prompt_rows} == EXPECTED_PROMPT_KEYS
        for row in prompt_rows:
            assert row["template"].strip(), f"{row['key']} system prompt is empty"
            assert row["user_template"].strip(), f"{row['key']} user prompt is empty"
            assert row["module"] == "social"
            assert row["version"] == 1
            assert _as_json(row["output_schema"]) == {"type": "object"}
            assert row["model_hint"] is None

        prompts = {row["key"]: row for row in prompt_rows}
        assert "real_help, pain_specificity" in prompts["social_intent"]["template"]
        assert "$title" in prompts["social_intent"]["user_template"]
        assert "{{LINK}}" in prompts["social_reply"]["template"]
        assert "$product_url" in prompts["social_reply"]["user_template"]
        assert "$previous_reply" in prompts["social_followup"]["user_template"]
        assert "$followup_index" in prompts["social_followup"]["user_template"]
    finally:
        await conn.close()
