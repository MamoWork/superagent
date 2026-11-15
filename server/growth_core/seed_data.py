"""Seed data and idempotent defaults for the growth tenant.

The prompt texts use ``string.Template`` placeholders (``$title``, ``$body``,
...) so callers can render them with the values available at run time. The
literal ``{{LINK}}`` marker is substituted later by the drafting pipeline.
"""

from __future__ import annotations

import json
import uuid

import asyncpg

SOCIAL_INTENT_SYSTEM = """You are a strict analyst for a founder-led growth team. Score one public post on
whether a helpful, disclosed reply from the founder would be appropriate. Return
JSON only. Do not invent facts. Use exactly these dimension ids:
real_help, pain_specificity, buyer_role, product_fit, reply_safety. Each
dimension score is an integer 0-10. Add a penalty only when the post is an ad,
already solved, stale (>90 days), duplicate, or competitor bait. Do not output a
total score; the server computes it.
"""

SOCIAL_INTENT_USER = """Platform: $platform
Community: $community
Post age (days): $age_days
Title: $title
Body:
$body
"""

SOCIAL_REPLY_SYSTEM = """You write a reply to a public post for a founder. Requirements:
1. Open by restating the specific problem in one sentence.
2. Give one concrete, useful suggestion or checklist that stands on its own.
3. Mention the product only if it directly fits; disclose "I built $product_name"
   or "I work on $product_name".
4. Include exactly one {{LINK}} placeholder, after the value section.
   Do not include any URL.
5. Do not promise results, fabricate customers, or criticize competitors.
6. Use the language of the original post.
Return JSON only:
{"body_markdown":"... {{LINK}} ...","link_path":"/features/...","risk_flags":[]}
"""

SOCIAL_REPLY_USER = """Platform: $platform
Community: $community
Title: $title
Body:
$body
Product: $product_name
Product site: $product_url
"""

SOCIAL_FOLLOWUP_SYSTEM = """Write a brief follow-up to a reply you sent one day ago. Add one new concrete
piece of value (a new example, check, or template). Do not repeat the first
reply. Include exactly one {{LINK}} placeholder after the value. Disclose
"I built $product_name" or "I work on $product_name". No promises, no pressure.
Use the original language. Return JSON only:
{"body_markdown":"... {{LINK}} ...","link_path":"/features/...","risk_flags":[]}
"""

SOCIAL_FOLLOWUP_USER = """Original post title: $title
Original post body: $body
Previous reply: $previous_reply
Follow-up number: $followup_index
Product: $product_name
"""

PROMPT_MODULE = "social"
PROMPT_VERSION = 1
PROMPT_OUTPUT_SCHEMA = {"type": "object"}

# (key, system prompt, user prompt)
PROMPT_TEMPLATES = (
    ("social_intent", SOCIAL_INTENT_SYSTEM, SOCIAL_INTENT_USER),
    ("social_reply", SOCIAL_REPLY_SYSTEM, SOCIAL_REPLY_USER),
    ("social_followup", SOCIAL_FOLLOWUP_SYSTEM, SOCIAL_FOLLOWUP_USER),
)

SCORING_RUBRIC_KEY = "social_intent"
SCORING_RUBRIC_VERSION = 1
SCORING_RUBRIC_DIMENSIONS = [
    {"id": "real_help", "weight": 30},
    {"id": "pain_specificity", "weight": 25},
    {"id": "buyer_role", "weight": 20},
    {"id": "product_fit", "weight": 15},
    {"id": "reply_safety", "weight": 10},
]
SCORING_RUBRIC_PENALTIES = [
    {"code": "ad", "points": -50},
    {"code": "already_solved", "points": -20},
    {"code": "stale_90d", "points": -20},
    {"code": "duplicate", "points": -30},
    {"code": "competitor_or_bait", "points": -50},
]
SCORING_RUBRIC_THRESHOLDS = {"qualified": 80, "watch": 60}

# (capability, provider, priority, config, secret_ref)
# secret_ref is an environment variable name only; no secrets are stored.
PROVIDER_CONFIGS = (
    (
        "social_source",
        "reddit",
        10,
        {"base_url": "https://www.reddit.com"},
        "GROWTH_REDDIT_USER_AGENT",
    ),
    (
        "social_source",
        "hackernews",
        20,
        {"base_url": "https://hn.algolia.com"},
        None,
    ),
    (
        "notifier",
        "feishu",
        10,
        {"chat_id_env": "GROWTH_FEISHU_CHAT_ID"},
        "GROWTH_FEISHU_APP_SECRET",
    ),
    (
        "llm",
        "openai_compatible",
        10,
        {"base_url": "https://api.openai.com/v1"},
        "GROWTH_LLM_API_KEY",
    ),
)

# (scope, scope_key, window_seconds, max_count)
RATE_LIMIT_RULES = (
    ("global", "*", 86400, 50),
    ("platform", "reddit", 86400, 5),
    ("subreddit", "*", 86400, 2),
)

QUOTA_METRIC = "social_replies"
QUOTA_PERIOD = "day"
QUOTA_LIMIT = 50

FEATURE_KEY = "social_module"


async def seed_tenant(
    conn: asyncpg.Connection,
    *,
    tenant_id: uuid.UUID,
    workspace_id: uuid.UUID,
    tenant_name: str = "Default",
    workspace_name: str = "Default",
) -> None:
    """Insert a tenant/workspace and all growth defaults idempotently.

    Safe to run repeatedly: every insert uses ``on conflict do nothing`` so
    existing configuration is never overwritten.
    """
    async with conn.transaction():
        await conn.execute(
            "insert into tenants (id, name) values ($1, $2) "
            "on conflict (id) do nothing",
            tenant_id,
            tenant_name,
        )
        await conn.execute(
            "insert into workspaces (id, tenant_id, name) values ($1, $2, $3) "
            "on conflict (id) do nothing",
            workspace_id,
            tenant_id,
            workspace_name,
        )

        for capability, provider, priority, config, secret_ref in PROVIDER_CONFIGS:
            await conn.execute(
                """
                insert into provider_configs
                    (tenant_id, capability, provider, priority, enabled, config,
                     secret_ref)
                values ($1, $2, $3, $4, true, $5::jsonb, $6)
                on conflict (tenant_id, capability, provider) do nothing
                """,
                tenant_id,
                capability,
                provider,
                priority,
                json.dumps(config),
                secret_ref,
            )

        await conn.execute(
            """
            insert into scoring_rubrics
                (tenant_id, key, version, dimensions, penalties, thresholds,
                 enabled)
            values ($1, $2, $3, $4::jsonb, $5::jsonb, $6::jsonb, true)
            on conflict (tenant_id, key, version) do nothing
            """,
            tenant_id,
            SCORING_RUBRIC_KEY,
            SCORING_RUBRIC_VERSION,
            json.dumps(SCORING_RUBRIC_DIMENSIONS),
            json.dumps(SCORING_RUBRIC_PENALTIES),
            json.dumps(SCORING_RUBRIC_THRESHOLDS),
        )

        await conn.execute(
            """
            insert into tenant_quotas
                (tenant_id, metric, period, limit_value, used_value, reset_at)
            values ($1, $2, $3, $4, 0, now() + interval '1 day')
            on conflict (tenant_id, metric, period) do nothing
            """,
            tenant_id,
            QUOTA_METRIC,
            QUOTA_PERIOD,
            QUOTA_LIMIT,
        )

        await conn.execute(
            """
            insert into tenant_features (tenant_id, feature_key, enabled)
            values ($1, $2, true)
            on conflict (tenant_id, feature_key) do nothing
            """,
            tenant_id,
            FEATURE_KEY,
        )

        for scope, scope_key, window_seconds, max_count in RATE_LIMIT_RULES:
            await conn.execute(
                """
                insert into rate_limit_rules
                    (tenant_id, workspace_id, channel, scope, scope_key,
                     window_seconds, max_count, enabled)
                values ($1, null, 'social', $2, $3, $4, $5, true)
                on conflict (tenant_id, channel, scope, scope_key) do nothing
                """,
                tenant_id,
                scope,
                scope_key,
                window_seconds,
                max_count,
            )

        for key, system_prompt, user_prompt in PROMPT_TEMPLATES:
            await conn.execute(
                """
                insert into prompt_templates
                    (tenant_id, key, module, version, template, user_template,
                     output_schema, model_hint, enabled)
                values ($1, $2, $3, $4, $5, $6, $7::jsonb, null, true)
                on conflict (tenant_id, key, version) do nothing
                """,
                tenant_id,
                key,
                PROMPT_MODULE,
                PROMPT_VERSION,
                system_prompt,
                user_prompt,
                json.dumps(PROMPT_OUTPUT_SCHEMA),
            )
