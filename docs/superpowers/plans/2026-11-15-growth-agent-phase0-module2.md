# Growth Agent Phase 0 + Module 2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the shared Growth Core and the first working social-interception pipeline: Reddit/HN ingestion, server-side intent scoring, one-link reply drafts, Feishu approval, manual send tracking, rate/suppression enforcement, and bounded follow-up.

**Architecture:** Add `growth_core` (Postgres repository, migrations, queue, outbox, adapters, Feishu, worker, internal API) and `growth_social` (Reddit/HN adapters, scoring, drafting, approval, sending, follow-up) beside the existing Opportunity Scout app. `growth_social` depends on `growth_core`; `growth_core` never imports `growth_social`. The existing SQLite app remains untouched except for a dependency-free `opportunity_core` extraction.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, asyncpg, httpx, OpenAI Python SDK, pytest + pytest-asyncio, Supabase Postgres, Feishu, n8n (external scheduler).

**Spec:** `docs/superpowers/specs/2026-11-15-growth-agent-design.md`

## Execution Prerequisite

`/Volumes/work/workspace/superAgent/ideas_pool` is **not currently a git repository**. Before Task 1, confirm with the user whether to run `git init` or to treat each “Commit” step as a checkpoint (skip `git`, record test output and files changed instead). Do not initialize git without explicit approval.

## Global Constraints

- v1 social sources: **Reddit + Hacker News only**. X is deferred to M2.5.
- Approval surface: **Feishu only**. No Telegram in v1.
- Intent threshold: **≥ 80 qualified**, **60–79 watch**, **< 60 drop**.
- Daily send limits: **Reddit 5/day**, **global 50/day**, **same-subreddit link-bearing replies ≤ 2/day**.
- Every reply contains **exactly one official link**, placed after the value section, with UTM, affiliation disclosure, and no shorteners/affiliate redirects.
- Follow-up: **max 1/day, max 3 total**; stop immediately on reply, unsubscribe, negative feedback, moderator warning, or suppression.
- Never auto-post, auto-comment, auto-DM, or automate a logged-in platform session. “Sent” is always a human-recorded action.
- All business tables carry `tenant_id`; operational tables also carry `workspace_id`. Statuses use `text + CHECK`, never database enums.
- Every externally-triggered job and outbox send has a unique idempotency/dedupe key.
- `n8n` must never write business tables directly. It calls `/internal/v1/*` with `X-Service-Token`; only the Python service writes business state.
- Secrets stay in environment variables (v1 `secret_ref` → env name) or Supabase Vault later. Never log, API-return, or store plaintext secrets in business tables.
- Existing Opportunity Scout tests must keep passing: `cd server && python -m pytest -q`.

## Review Focus

These are the failure modes most likely to bite a real operator. Each gets an owning task and a test.

1. **Duplicate delivery.** n8n retries, Feishu replays a callback, or a worker crashes after claiming a task; the same post, draft, card, or sent message must not be created twice.
2. **Unsafe LLM output.** The model returns zero or multiple links, a shortener, a homepage, an external URL, or omits the disclosure; the draft must be rejected, never approved or sent.
3. **Limits checked only at draft time.** A message approved yesterday and sent today must still be blocked by today’s global/Reddit/subreddit limits at the moment of recording the send.
4. **Feedback after draft.** A user replies negatively, unsubscribes, or a moderator warns after a draft is queued; all pending follow-ups and sends for that lead must stop.
5. **Crash between external send and local commit.** A Feishu card may already exist when the outbox retries; the retry must not create a second card/approval request.

## File Structure

Create:

```
server/opportunity_core/
├── __init__.py
├── models.py
└── providers/
    ├── __init__.py
    ├── base.py
    └── registry.py

server/growth_core/
├── __init__.py
├── config.py
├── db.py
├── migrate.py
├── seed_data.py
├── schemas.py
├── migrations/
│   ├── 0001_core.sql
│   ├── 0002_social.sql
│   └── 0003_rls.sql
├── scripts/
│   ├── __init__.py
│   └── seed.py
├── repositories/
│   ├── __init__.py
│   ├── base.py
│   └── postgres.py
├── adapters/
│   ├── __init__.py
│   ├── base.py
│   ├── registry.py
│   ├── feishu.py
│   └── llm.py
├── services/
│   ├── __init__.py
│   ├── outbox.py
│   ├── ratelimit.py
│   ├── worker.py
│   └── feishu_signature.py
└── api/
    ├── __init__.py
    ├── deps.py
    └── core.py

server/growth_social/
├── __init__.py
├── adapters/
│   ├── __init__.py
│   ├── reddit.py
│   └── hackernews.py
├── services/
│   ├── __init__.py
│   ├── prompts.py
│   ├── link_policy.py
│   ├── ingest.py
│   ├── scoring.py
│   ├── drafting.py
│   ├── cards.py
│   ├── approval.py
│   ├── sending.py
│   └── followup.py
├── handlers.py
├── api.py
├── main.py
└── worker.py

server/tests/growth/
├── conftest.py
├── fakes.py
├── test_growth_core_config.py
├── test_migrations.py
├── test_repository_memory.py
├── test_api_auth.py
├── test_feishu.py
├── test_registry.py
├── test_worker_outbox.py
├── test_reddit_adapter.py
├── test_hackernews_adapter.py
├── test_ingest.py
├── test_llm.py
├── test_scoring.py
├── test_link_policy.py
├── test_drafting.py
├── test_approval.py
├── test_sending.py
├── test_followup.py
├── test_social_e2e.py
└── test_postgres_integration.py
```

Modify:

```
server/requirements.txt          # add asyncpg, pytest-asyncio
server/pytest.ini                # asyncio_mode + integration marker
server/app/schemas.py            # import+re-export moved models
server/app/providers/base.py     # compatibility shim
server/app/providers/registry.py # import ProviderRegistry from core
server/README.md                 # short Growth section
```

Add:

```
server/.env.growth.example
server/docs/growth-runbook.md
```

---

## Task 1: Growth package scaffold, settings, dependencies, test bootstrap

**Files:**
- Create: `server/growth_core/__init__.py`
- Create: `server/growth_core/config.py`
- Create: `server/growth_social/__init__.py`
- Create: `server/tests/growth/__init__.py`
- Create: `server/tests/growth/conftest.py`
- Modify: `server/requirements.txt`
- Modify: `server/pytest.ini`
- Test: `server/tests/growth/test_growth_core_config.py`

**Interfaces:**
- Produces:
  - `GrowthConfigError(Exception)`
  - `GrowthSettings` frozen dataclass with the fields below
  - `GrowthSettings.from_env() -> GrowthSettings`

```python
@dataclass(frozen=True)
class GrowthSettings:
    database_url: str = field(repr=False)
    service_token: str = field(repr=False)
    tenant_id: str
    workspace_id: str
    feishu_app_id: str = ""
    feishu_app_secret: str = field(default="", repr=False)
    feishu_verification_token: str = field(default="", repr=False)
    feishu_encrypt_key: str = field(default="", repr=False)
    feishu_chat_id: str = ""
    feishu_base_url: str = "https://open.feishu.cn"
    reddit_user_agent: str = "growth-agent/0.1"
    reddit_base_url: str = "https://www.reddit.com"
    hn_base_url: str = "https://hn.algolia.com"
    llm_model: str = ""
    llm_scoring_model: str = ""
    llm_drafting_model: str = ""
    llm_base_url: str = ""
    llm_api_key: str = field(default="", repr=False)
    llm_timeout_seconds: float = 60.0
    product_name: str = ""
    product_url: str = ""
    product_domain: str = ""
    global_daily_limit: int = 50
    reddit_daily_limit: int = 5
    subreddit_link_daily_limit: int = 2
    followup_max_total: int = 3
    followup_min_interval_hours: int = 24
    worker_id: str = "growth-worker-1"
    worker_poll_seconds: float = 2.0
    stale_lock_seconds: int = 600
```

- [ ] **Step 1: Write the failing test**

```python
import pytest

from growth_core.config import GrowthConfigError, GrowthSettings


def test_growth_settings_from_env(monkeypatch):
    monkeypatch.setenv("GROWTH_DATABASE_URL", "postgresql://u:p@localhost/db")
    monkeypatch.setenv("GROWTH_SERVICE_TOKEN", "test-token")
    monkeypatch.setenv("GROWTH_TENANT_ID", "00000000-0000-0000-0000-000000000001")
    monkeypatch.setenv("GROWTH_WORKSPACE_ID", "00000000-0000-0000-0000-000000000002")
    settings = GrowthSettings.from_env()
    assert settings.database_url == "postgresql://u:p@localhost/db"
    assert settings.global_daily_limit == 50
    assert settings.reddit_daily_limit == 5
    assert settings.followup_max_total == 3
    assert settings.followup_min_interval_hours == 24


def test_missing_required_env_raises(monkeypatch):
    monkeypatch.delenv("GROWTH_DATABASE_URL", raising=False)
    with pytest.raises(GrowthConfigError, match="GROWTH_DATABASE_URL"):
        GrowthSettings.from_env()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd server && python -m pytest tests/growth/test_growth_core_config.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'growth_core'`.

- [ ] **Step 3: Implement `GrowthSettings.from_env` and add dependencies**

`config.py` reads `os.environ`; required keys are `GROWTH_DATABASE_URL`, `GROWTH_SERVICE_TOKEN`, `GROWTH_TENANT_ID`, `GROWTH_WORKSPACE_ID`. Missing key raises `GrowthConfigError` naming the env var. Cast integer/float fields with the names in the dataclass.

Add to `server/requirements.txt`:

```text
asyncpg>=0.29
pytest-asyncio>=0.24
```

Update `server/pytest.ini`:

```ini
[pytest]
pythonpath = .
testpaths = tests
asyncio_mode = auto
markers =
    integration: requires GROWTH_TEST_DATABASE_URL
```

`tests/growth/conftest.py` defines the shared fixed clock:

```python
from datetime import datetime, timezone
import pytest

@pytest.fixture
def now() -> datetime:
    return datetime(2026, 11, 15, 9, 0, tzinfo=timezone.utc)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd server && python -m pytest tests/growth/test_growth_core_config.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add server/growth_core server/growth_social server/tests/growth server/requirements.txt server/pytest.ini
git commit -m "feat: scaffold growth core and settings"
```

---

## Task 2: Extract `opportunity_core` without changing existing behavior

**Files:**
- Create: `server/opportunity_core/__init__.py`
- Create: `server/opportunity_core/models.py`
- Create: `server/opportunity_core/providers/__init__.py`
- Create: `server/opportunity_core/providers/base.py`
- Create: `server/opportunity_core/providers/registry.py`
- Modify: `server/app/schemas.py:1-56`
- Modify: `server/app/providers/base.py`
- Modify: `server/app/providers/registry.py:1-27`
- Test: `server/tests/test_opportunity_core.py`

**Interfaces:**
- Produces:
  - `opportunity_core.models`: `ProviderStatus`, `AuthKind`, `Capability`, `ProviderInfo`, `ProviderHealth`, `SearchQuery`, `Signal`
  - `opportunity_core.providers.base`: `ProviderError`, `SourceProvider`
  - `opportunity_core.providers.registry`: `ProviderRegistry`
- Compatibility: `app.schemas`, `app.providers.base`, and `app.providers.registry` must re-export the same objects.

- [ ] **Step 1: Write the failing test**

```python
def test_opportunity_core_is_the_same_contract():
    from app.schemas import Signal as AppSignal
    from opportunity_core import Signal as CoreSignal
    from app.providers.base import SourceProvider as AppProvider
    from opportunity_core.providers.base import SourceProvider as CoreProvider

    assert AppSignal is CoreSignal
    assert AppProvider is CoreProvider
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd server && python -m pytest tests/test_opportunity_core.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'opportunity_core'`.

- [ ] **Step 3: Move models and provider contracts**

Move the exact definitions of `ProviderStatus`, `AuthKind`, `Capability`, `ProviderInfo`, `ProviderHealth`, `SearchQuery`, and `Signal` from `app/schemas.py` into `opportunity_core/models.py`. Keep `ProviderErrorInfo` in `app/schemas.py` because it is API-specific.

`opportunity_core/__init__.py` re-exports those seven names (`from opportunity_core.models import ...` plus `__all__`), so `from opportunity_core import Signal` works.

At the top of `app/schemas.py`, replace the moved definitions with:

```python
from opportunity_core.models import (
    AuthKind,
    Capability,
    ProviderHealth,
    ProviderInfo,
    ProviderStatus,
    SearchQuery,
    Signal,
)
```

Move `ProviderError` and `SourceProvider` into `opportunity_core/providers/base.py`, importing models from `opportunity_core.models`. Replace `app/providers/base.py` with:

```python
from opportunity_core.providers.base import ProviderError, SourceProvider

__all__ = ["ProviderError", "SourceProvider"]
```

Move `ProviderRegistry` into `opportunity_core/providers/registry.py`, importing from `opportunity_core.models` and `opportunity_core.providers.base`. In `app/providers/registry.py`, keep `build_registry(settings)` but import `ProviderRegistry` from `opportunity_core.providers.registry`.

Do not move `AnalysisEngine` or analyzer code in this task; it depends on app-specific `Run`, `DomainPack`, and `AnalysisDraft`, and is only needed by Phase 3.

- [ ] **Step 4: Run the full existing suite plus the new test**

Run: `cd server && python -m pytest -q`
Expected: all existing tests pass and `test_opportunity_core_is_the_same_contract` passes.

- [ ] **Step 5: Commit**

```bash
git add server/opportunity_core server/app/schemas.py server/app/providers server/tests/test_opportunity_core.py
git commit -m "refactor: extract opportunity core contracts"
```

---

## Task 3: Migration runner and core schema

**Files:**
- Create: `server/growth_core/db.py`
- Create: `server/growth_core/migrate.py`
- Create: `server/growth_core/migrations/0001_core.sql`
- Test: `server/tests/growth/test_migrations.py`

**Interfaces:**
- Produces:
  - `async def create_pool(database_url: str) -> asyncpg.Pool`
  - `async def apply_migrations(database_url: str, migrations_dir: Path | None = None) -> list[str]`
  - CLI: `python -m growth_core.migrate --database-url <dsn>`

- [ ] **Step 1: Write the failing test**

```python
import os
import pytest

from growth_core.migrate import apply_migrations

pytestmark = pytest.mark.integration


@pytest.mark.skipif(
    not os.getenv("GROWTH_TEST_DATABASE_URL"),
    reason="GROWTH_TEST_DATABASE_URL is not set",
)
async def test_migrations_are_idempotent():
    url = os.environ["GROWTH_TEST_DATABASE_URL"]
    first = await apply_migrations(url)
    second = await apply_migrations(url)
    assert "0001_core" in first
    assert second == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd server && GROWTH_TEST_DATABASE_URL=postgresql://... python -m pytest tests/growth/test_migrations.py -q`
Expected: FAIL because `growth_core.migrate` does not exist.

- [ ] **Step 3: Implement the runner and `0001_core.sql`**

`migrate.py` sorts `*.sql` by filename, ensures `schema_migrations(version, applied_at)`, and for each unapplied file runs the script and inserts its stem inside one transaction. `main()` parses `--database-url` (default `GROWTH_DATABASE_URL`) and `--migrations-dir`.

`0001_core.sql`:

```sql
create extension if not exists pgcrypto;

create table if not exists schema_migrations (
  version text primary key,
  applied_at timestamptz not null default now()
);

create table if not exists tenants (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  created_at timestamptz not null default now()
);

create table if not exists workspaces (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references tenants(id) on delete cascade,
  name text not null,
  created_at timestamptz not null default now()
);
create index if not exists workspaces_tenant_idx on workspaces(tenant_id);

create table if not exists memberships (
  tenant_id uuid not null references tenants(id) on delete cascade,
  user_id uuid not null,
  role text not null check (role in ('owner','admin','member','viewer')),
  created_at timestamptz not null default now(),
  primary key (tenant_id, user_id)
);

create table if not exists platform_registry (
  platform text primary key,
  display_name text not null,
  enabled boolean not null default true
);

create table if not exists channel_registry (
  channel text primary key,
  display_name text not null,
  enabled boolean not null default true
);

create table if not exists content_type_registry (
  content_type text primary key,
  display_name text not null,
  enabled boolean not null default true
);

create table if not exists provider_configs (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references tenants(id) on delete cascade,
  capability text not null,
  provider text not null,
  priority int not null default 100,
  enabled boolean not null default true,
  config jsonb not null default '{}'::jsonb,
  secret_ref text,
  config_schema_version int not null default 1,
  version int not null default 1,
  updated_by text,
  updated_at timestamptz not null default now(),
  unique (tenant_id, capability, provider)
);
create index if not exists provider_configs_lookup_idx
  on provider_configs(tenant_id, capability, enabled, priority);

create table if not exists tenant_quotas (
  tenant_id uuid not null references tenants(id) on delete cascade,
  metric text not null,
  period text not null check (period in ('day','month')),
  limit_value int not null,
  used_value int not null default 0,
  reset_at timestamptz not null,
  version int not null default 1,
  updated_at timestamptz not null default now(),
  primary key (tenant_id, metric, period)
);

create table if not exists tenant_features (
  tenant_id uuid not null references tenants(id) on delete cascade,
  feature_key text not null,
  enabled boolean not null default false,
  config jsonb not null default '{}'::jsonb,
  version int not null default 1,
  updated_at timestamptz not null default now(),
  primary key (tenant_id, feature_key)
);

create table if not exists config_versions (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references tenants(id) on delete cascade,
  table_name text not null,
  record_id uuid not null,
  version int not null,
  diff jsonb not null,
  snapshot jsonb not null default '{}'::jsonb,
  changed_by text,
  created_at timestamptz not null default now()
);
create index if not exists config_versions_record_idx
  on config_versions(tenant_id, table_name, record_id, version desc);

create table if not exists prompt_templates (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references tenants(id) on delete cascade,
  key text not null,
  module text not null,
  version int not null,
  template text not null,
  output_schema jsonb not null,
  model_hint text,
  enabled boolean not null default true,
  created_at timestamptz not null default now(),
  unique (tenant_id, key, version)
);

create table if not exists scoring_rubrics (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references tenants(id) on delete cascade,
  key text not null,
  version int not null,
  dimensions jsonb not null,
  penalties jsonb not null,
  thresholds jsonb not null,
  enabled boolean not null default true,
  created_at timestamptz not null default now(),
  unique (tenant_id, key, version)
);

create table if not exists pipeline_runs (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references tenants(id) on delete cascade,
  workspace_id uuid not null references workspaces(id) on delete cascade,
  pipeline text not null,
  task_type text not null,
  payload jsonb not null default '{}'::jsonb,
  status text not null check (status in ('queued','running','succeeded','failed','dead')),
  priority int not null default 100,
  idempotency_key text not null,
  run_after timestamptz not null default now(),
  locked_at timestamptz,
  locked_by text,
  attempts int not null default 0,
  max_attempts int not null default 5,
  last_error text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (tenant_id, idempotency_key)
);
create index if not exists pipeline_runs_claim_idx
  on pipeline_runs(status, priority, run_after);
create index if not exists pipeline_runs_tenant_idx
  on pipeline_runs(tenant_id, status);

create table if not exists outbox_messages (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references tenants(id) on delete cascade,
  workspace_id uuid not null references workspaces(id) on delete cascade,
  topic text not null,
  payload jsonb not null,
  status text not null check (status in ('pending','sending','sent','failed','dead')),
  idempotency_key text not null,
  attempts int not null default 0,
  next_attempt_at timestamptz not null default now(),
  last_error text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (tenant_id, idempotency_key)
);
create index if not exists outbox_claim_idx
  on outbox_messages(status, next_attempt_at);

create table if not exists audit_log (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references tenants(id) on delete cascade,
  workspace_id uuid references workspaces(id) on delete set null,
  actor_type text not null check (actor_type in ('user','service','n8n','system')),
  actor_id text,
  action text not null,
  entity_type text not null,
  entity_id uuid,
  before jsonb,
  after jsonb,
  created_at timestamptz not null default now()
);
create index if not exists audit_log_tenant_time_idx
  on audit_log(tenant_id, created_at desc);

create table if not exists provider_health (
  tenant_id uuid not null references tenants(id) on delete cascade,
  capability text not null,
  provider text not null,
  status text not null check (status in ('closed','open','half_open')),
  failure_count int not null default 0,
  last_error text,
  last_checked_at timestamptz,
  opened_at timestamptz,
  primary key (tenant_id, capability, provider)
);
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd server && GROWTH_TEST_DATABASE_URL=postgresql://... python -m pytest tests/growth/test_migrations.py -q`
Expected: PASS; the second run returns `[]`.

- [ ] **Step 5: Commit**

```bash
git add server/growth_core/db.py server/growth_core/migrate.py server/growth_core/migrations/0001_core.sql server/tests/growth/test_migrations.py
git commit -m "feat: add postgres migration runner and core schema"
```

---

## Task 4: Social schema and RLS

**Files:**
- Create: `server/growth_core/migrations/0002_social.sql`
- Create: `server/growth_core/migrations/0003_rls.sql`
- Modify: `server/tests/growth/test_migrations.py`
- Test: `server/tests/growth/test_migrations.py`

**Interfaces:**
- Produces tables: `growth_sources`, `social_leads`, `outreach_messages`, `outreach_versions`, `approval_requests`, `rate_limit_rules`, `rate_limit_counters`, `suppression_list`, `delivery_log`.
- Produces RLS policy name: `tenant_isolation` on every tenant-scoped table.

- [ ] **Step 1: Write the failing schema test**

```python
import uuid

@pytest.mark.integration
@pytest.mark.skipif(not os.getenv("GROWTH_TEST_DATABASE_URL"), reason="no test DB")
async def test_social_tables_exist_and_status_is_constrained():
    import asyncpg
    url = os.environ["GROWTH_TEST_DATABASE_URL"]
    await apply_migrations(url)
    conn = await asyncpg.connect(url)
    try:
        tables = await conn.fetch(
            "select tablename from pg_tables where schemaname = 'public'"
        )
        names = {row["tablename"] for row in tables}
        assert {"growth_sources", "social_leads", "outreach_messages",
                "outreach_versions", "approval_requests", "delivery_log"} <= names
        tenant_id, workspace_id = uuid.uuid4(), uuid.uuid4()
        await conn.execute("insert into tenants(id, name) values($1, 't')", tenant_id)
        await conn.execute(
            "insert into workspaces(id, tenant_id, name) values($1, $2, 'w')",
            workspace_id, tenant_id,
        )
        with pytest.raises(asyncpg.CheckViolationError):
            await conn.execute(
                "insert into social_leads (tenant_id, workspace_id, platform, "
                "platform_post_id, source_url, dedupe_key, status) "
                "values ($1, $2, 'reddit', 'x', 'https://example.com', 'x', "
                "'not-a-status')",
                tenant_id, workspace_id,
            )
    finally:
        await conn.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd server && GROWTH_TEST_DATABASE_URL=postgresql://... python -m pytest tests/growth/test_migrations.py -q`
Expected: FAIL because the social tables do not exist.

- [ ] **Step 3: Add `0002_social.sql` and `0003_rls.sql`**

`0002_social.sql`:

```sql
create table if not exists growth_sources (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references tenants(id) on delete cascade,
  workspace_id uuid not null references workspaces(id) on delete cascade,
  source_type text not null,
  platform text not null,
  dedupe_key text not null,
  config jsonb not null default '{}'::jsonb,
  cadence_minutes int not null default 30,
  enabled boolean not null default true,
  last_run_at timestamptz,
  last_error text,
  version int not null default 1,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (tenant_id, dedupe_key)
);
create index if not exists growth_sources_enabled_idx
  on growth_sources(tenant_id, enabled, source_type);

create table if not exists social_leads (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references tenants(id) on delete cascade,
  workspace_id uuid not null references workspaces(id) on delete cascade,
  source_id uuid references growth_sources(id) on delete set null,
  platform text not null,
  platform_post_id text not null,
  title text not null default '',
  body text not null default '',
  author_public text,
  source_url text not null,
  published_at timestamptz,
  metrics jsonb not null default '{}'::jsonb,
  raw jsonb,
  subreddit text,
  subreddit_rules jsonb not null default '{}'::jsonb,
  score int check (score between 0 and 100),
  score_reasons jsonb,
  model text,
  prompt_version text,
  status text not null check (status in (
    'discovered','scored','qualified','draft_ready','approved','sent',
    'replied','converted','dropped','watch','suppressed','rejected'
  )),
  dedupe_key text not null,
  version int not null default 1,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (tenant_id, dedupe_key)
);
create index if not exists social_leads_list_idx
  on social_leads(tenant_id, platform, status, created_at desc);

create table if not exists outreach_messages (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references tenants(id) on delete cascade,
  workspace_id uuid not null references workspaces(id) on delete cascade,
  channel text not null,
  provider text,
  lead_id uuid references social_leads(id) on delete cascade,
  user_id uuid,
  rule_key text,
  status text not null check (status in (
    'draft_ready','approved','sent','replied','converted',
    'rejected','suppressed','failed','expired'
  )),
  scheduled_at timestamptz,
  sent_at timestamptz,
  provider_message_id text,
  dedupe_key text not null,
  metadata jsonb not null default '{}'::jsonb,
  version int not null default 1,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (tenant_id, dedupe_key)
);
create index if not exists outreach_messages_list_idx
  on outreach_messages(tenant_id, channel, status, scheduled_at);

create table if not exists outreach_versions (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references tenants(id) on delete cascade,
  workspace_id uuid references workspaces(id) on delete cascade,
  message_id uuid not null references outreach_messages(id) on delete cascade,
  version int not null,
  subject text,
  body_text text not null,
  cta_url text,
  model text,
  prompt_version text,
  risk_flags jsonb not null default '[]'::jsonb,
  approved_by text,
  approved_at timestamptz,
  created_at timestamptz not null default now(),
  unique (tenant_id, message_id, version)
);

create table if not exists approval_requests (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references tenants(id) on delete cascade,
  workspace_id uuid not null references workspaces(id) on delete cascade,
  message_id uuid not null references outreach_messages(id) on delete cascade,
  approval_id text not null,
  provider text not null default 'feishu',
  external_id text,
  status text not null check (status in ('pending','approved','rejected','expired')),
  decided_by text,
  decided_at timestamptz,
  reason text,
  payload jsonb not null default '{}'::jsonb,
  version int not null default 1,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (tenant_id, approval_id)
);
create index if not exists approval_requests_pending_idx
  on approval_requests(tenant_id, status, created_at);

create table if not exists rate_limit_rules (
  tenant_id uuid not null references tenants(id) on delete cascade,
  workspace_id uuid references workspaces(id) on delete cascade,
  channel text not null,
  scope text not null check (scope in ('global','platform','subreddit','user')),
  scope_key text not null default '*',
  window_seconds int not null,
  max_count int not null,
  enabled boolean not null default true,
  version int not null default 1,
  updated_by text,
  updated_at timestamptz not null default now(),
  primary key (tenant_id, channel, scope, scope_key)
);

create table if not exists rate_limit_counters (
  tenant_id uuid not null references tenants(id) on delete cascade,
  workspace_id uuid references workspaces(id) on delete cascade,
  channel text not null,
  scope text not null,
  scope_key text not null,
  window_start timestamptz not null,
  count int not null default 0,
  primary key (tenant_id, channel, scope, scope_key, window_start)
);

create table if not exists suppression_list (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references tenants(id) on delete cascade,
  workspace_id uuid references workspaces(id) on delete cascade,
  kind text not null check (kind in ('email','platform_user','domain')),
  value text not null,
  reason text not null check (reason in (
    'unsubscribe','hard_bounce','complaint','manual',
    'negative_reply','moderator_warning'
  )),
  source text,
  created_at timestamptz not null default now(),
  unique (tenant_id, kind, value)
);

create table if not exists delivery_log (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references tenants(id) on delete cascade,
  workspace_id uuid not null references workspaces(id) on delete cascade,
  message_id uuid references outreach_messages(id) on delete set null,
  lead_id uuid references social_leads(id) on delete set null,
  provider text not null,
  event_type text not null,
  payload jsonb not null default '{}'::jsonb,
  received_at timestamptz not null default now()
);
create index if not exists delivery_log_message_idx
  on delivery_log(tenant_id, message_id, received_at desc);
```

`outreach_versions`, `rate_limit_rules`, `rate_limit_counters`, and `suppression_list` carry `workspace_id` as a nullable FK because they are written from tenant-level operations (versioning, rate enforcement, suppression) that do not always carry a workspace; rows created from a workspace context set it. `outreach_versions` has no `status`/`updated_at` because versions are immutable.

`0003_rls.sql`:

```sql
create schema if not exists auth;
create or replace function auth.jwt() returns jsonb
language sql stable as $$
  select coalesce(nullif(current_setting('request.jwt.claims', true), ''), '{}')::jsonb
$$;

do $$
declare
  t text;
begin
  foreach t in array array[
    'workspaces','memberships','provider_configs','tenant_quotas','tenant_features',
    'config_versions','prompt_templates','scoring_rubrics','pipeline_runs','outbox_messages',
    'audit_log','provider_health','growth_sources','social_leads','outreach_messages',
    'outreach_versions','approval_requests','rate_limit_rules','rate_limit_counters',
    'suppression_list','delivery_log'
  ] loop
    execute format('alter table %I enable row level security', t);
    execute format('drop policy if exists tenant_isolation on %I', t);
    execute format(
      'create policy tenant_isolation on %I using '
      '(tenant_id = (auth.jwt() ->> ''tenant_id'')::uuid) with check '
      '(tenant_id = (auth.jwt() ->> ''tenant_id'')::uuid)',
      t
    );
  end loop;
end $$;
```

Note: `workspaces`, `memberships`, and all tenant-scoped tables have `tenant_id`; `tenants` itself is not in the policy list. The Python service uses the Supabase service role or a superuser-equivalent role and bypasses RLS; the policies protect direct JWT-scoped access.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd server && GROWTH_TEST_DATABASE_URL=postgresql://... python -m pytest tests/growth/test_migrations.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add server/growth_core/migrations/0002_social.sql server/growth_core/migrations/0003_rls.sql server/tests/growth/test_migrations.py
git commit -m "feat: add social schema and tenant RLS"
```

---

## Task 5: Seed script for tenant, providers, rate rules, prompts, rubric

**Files:**
- Create: `server/growth_core/seed_data.py`
- Create: `server/growth_core/scripts/__init__.py`
- Create: `server/growth_core/scripts/seed.py`
- Create: `server/growth_core/migrations/0004_prompt_user_template.sql`
- Test: `server/tests/growth/test_seed.py`

**Interfaces:**
- Produces:
  - `async def seed_tenant(conn: asyncpg.Connection, *, tenant_id: UUID, workspace_id: UUID, tenant_name: str = "Default", workspace_name: str = "Default") -> None`
  - CLI: `python -m growth_core.scripts.seed --tenant-id <uuid> --workspace-id <uuid>`
- Seed keys: `social_intent`, `social_reply`, `social_followup` prompt templates; `social_intent` scoring rubric; rate rules `global/*=50`, `platform/reddit=5`, `subreddit/*=2`.

- [ ] **Step 1: Write the failing test**

```python
import os
import uuid
import pytest
import asyncpg
from growth_core.migrate import apply_migrations
from growth_core.scripts.seed import seed_tenant

pytestmark = pytest.mark.integration

@pytest.mark.skipif(not os.getenv("GROWTH_TEST_DATABASE_URL"), reason="no test DB")
async def test_seed_is_idempotent():
    url = os.environ["GROWTH_TEST_DATABASE_URL"]
    await apply_migrations(url)
    tenant_id, workspace_id = uuid.uuid4(), uuid.uuid4()
    conn = await asyncpg.connect(url)
    try:
        await seed_tenant(conn, tenant_id=tenant_id, workspace_id=workspace_id)
        await seed_tenant(conn, tenant_id=tenant_id, workspace_id=workspace_id)
        count = await conn.fetchval(
            "select count(*) from rate_limit_rules where tenant_id = $1", tenant_id
        )
        assert count == 3
        keys = {r["key"] for r in await conn.fetch(
            "select key from prompt_templates where tenant_id = $1", tenant_id
        )}
        assert keys == {"social_intent", "social_reply", "social_followup"}
    finally:
        await conn.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd server && GROWTH_TEST_DATABASE_URL=postgresql://... python -m pytest tests/growth/test_seed.py -q`
Expected: FAIL because `seed_tenant` does not exist.

- [ ] **Step 3: Implement seed constants and idempotent inserts**

`seed_tenant` first inserts the `tenants` and `workspaces` rows if missing (`insert ... on conflict do nothing`), then all defaults. `seed_data.py` defines the exact prompt strings, rubric JSON, and rate rules. Use `string.Template` placeholders (`$title`, `$body`, `$platform`, `$community`, `$age_days`, `$product_name`, `$product_url`, `$previous_reply`, `$followup_index`).

`prompt_templates` stores the system prompt in `template`; the user prompt lives in a new `user_template text not null default ''` column added by `0004_prompt_user_template.sql` (`alter table prompt_templates add column if not exists user_template text not null default ''`). Seed each prompt row with `module='social'`, `version=1`, `output_schema={"type": "object"}`, `model_hint=NULL` (models come from settings), and both prompt texts.

`SOCIAL_INTENT_SYSTEM`:

```text
You are a strict analyst for a founder-led growth team. Score one public post on
whether a helpful, disclosed reply from the founder would be appropriate. Return
JSON only. Do not invent facts. Use exactly these dimension ids:
real_help, pain_specificity, buyer_role, product_fit, reply_safety. Each
dimension score is an integer 0-10. Add a penalty only when the post is an ad,
already solved, stale (>90 days), duplicate, or competitor bait. Do not output a
total score; the server computes it.
```

`SOCIAL_INTENT_USER`:

```text
Platform: $platform
Community: $community
Post age (days): $age_days
Title: $title
Body:
$body
```

`SOCIAL_REPLY_SYSTEM`:

```text
You write a reply to a public post for a founder. Requirements:
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
```

`SOCIAL_REPLY_USER`:

```text
Platform: $platform
Community: $community
Title: $title
Body:
$body
Product: $product_name
Product site: $product_url
```

`SOCIAL_FOLLOWUP_SYSTEM`:

```text
Write a brief follow-up to a reply you sent one day ago. Add one new concrete
piece of value (a new example, check, or template). Do not repeat the first
reply. Include exactly one {{LINK}} placeholder after the value. Disclose
"I built $product_name" or "I work on $product_name". No promises, no pressure.
Use the original language. Return JSON only:
{"body_markdown":"... {{LINK}} ...","link_path":"/features/...","risk_flags":[]}
```

`SOCIAL_FOLLOWUP_USER`:

```text
Original post title: $title
Original post body: $body
Previous reply: $previous_reply
Follow-up number: $followup_index
Product: $product_name
```

Rubric JSON:

```json
{
  "dimensions": [
    {"id": "real_help", "weight": 30},
    {"id": "pain_specificity", "weight": 25},
    {"id": "buyer_role", "weight": 20},
    {"id": "product_fit", "weight": 15},
    {"id": "reply_safety", "weight": 10}
  ],
  "penalties": [
    {"code": "ad", "points": -50},
    {"code": "already_solved", "points": -20},
    {"code": "stale_90d", "points": -20},
    {"code": "duplicate", "points": -30},
    {"code": "competitor_or_bait", "points": -50}
  ],
  "thresholds": {"qualified": 80, "watch": 60}
}
```

Seed provider configs:

```text
("social_source", "reddit", 10, {"base_url": "https://www.reddit.com"}, "GROWTH_REDDIT_USER_AGENT")
("social_source", "hackernews", 20, {"base_url": "https://hn.algolia.com"}, null)
("notifier", "feishu", 10, {"chat_id_env": "GROWTH_FEISHU_CHAT_ID"}, "GROWTH_FEISHU_APP_SECRET")
("llm", "openai_compatible", 10, {"base_url": "https://api.openai.com/v1"}, "GROWTH_LLM_API_KEY")
```

The scoring and drafting model names are **not** stored in the provider config; they come from `GrowthSettings.llm_scoring_model` and `GrowthSettings.llm_drafting_model` so the cheap/strong split is configurable without a config row. The seeded config only provides the OpenAI-compatible `base_url`; the API key comes from `secret_ref`.

Seed rate rules with `insert ... on conflict do nothing` (tenant-level rows leave `workspace_id` null):

```sql
('social', 'global', '*', 86400, 50)
('social', 'platform', 'reddit', 86400, 5)
('social', 'subreddit', '*', 86400, 2)
```

Also insert `tenant_quotas(metric='social_replies', period='day', limit_value=50)` and `tenant_features(feature_key='social_module', enabled=true)`.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd server && GROWTH_TEST_DATABASE_URL=postgresql://... python -m pytest tests/growth/test_seed.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add server/growth_core/seed_data.py server/growth_core/scripts server/tests/growth/test_seed.py
git commit -m "feat: seed growth tenant defaults"
```

---

## Task 6: Repository protocol and Postgres implementation

**Files:**
- Create: `server/growth_core/schemas.py`
- Create: `server/growth_core/repositories/__init__.py`
- Create: `server/growth_core/repositories/base.py`
- Create: `server/growth_core/repositories/postgres.py`
- Test: `server/tests/growth/test_repository_postgres.py`

**Interfaces:**
- Produces models in `growth_core.schemas`: `NewTask`, `PipelineTask`, `NewOutboxMessage`, `OutboxMessage`, `ProviderConfig`, `PromptTemplate`, `ScoringRubric`, `RateLimitRule`, `RateLimitCheck`, `RateLimitDecision`, `NewAuditEntry`, `GrowthSource`, `NewSocialLead`, `SocialLead`, `NewOutreachMessage`, `OutreachMessage`, `NewOutreachVersion`, `OutreachVersion`, `NewApprovalRequest`, `ApprovalRequest`, `NewDeliveryLog`.
- Produces `GrowthRepository` protocol in `repositories/base.py` with these exact methods:

```python
class GrowthRepository(Protocol):
    async def list_provider_configs(self, tenant_id: UUID, capability: str) -> list[ProviderConfig]: ...
    async def get_prompt_template(self, tenant_id: UUID, key: str, version: int | None = None) -> PromptTemplate | None: ...
    async def get_scoring_rubric(self, tenant_id: UUID, key: str, version: int | None = None) -> ScoringRubric | None: ...
    async def get_feature(self, tenant_id: UUID, feature_key: str) -> bool: ...
    async def list_rate_limit_rules(self, tenant_id: UUID, channel: str) -> list[RateLimitRule]: ...
    async def ensure_tenant(self, tenant_id: UUID, workspace_id: UUID) -> None: ...
    async def add_source(self, source: GrowthSource) -> None: ...
    async def close(self) -> None: ...

    async def enqueue_task(self, task: NewTask) -> UUID: ...
    async def claim_task(self, worker_id: str, now: datetime | None = None) -> PipelineTask | None: ...
    async def complete_task(self, task_id: UUID, worker_id: str | None = None) -> None: ...
    async def fail_task(self, task_id: UUID, error: str, now: datetime | None = None, worker_id: str | None = None) -> None: ...
    async def reclaim_stale_tasks(self, older_than_seconds: int, now: datetime | None = None) -> int: ...

    async def enqueue_outbox(self, message: NewOutboxMessage) -> UUID: ...
    async def claim_outbox(self, limit: int = 10, now: datetime | None = None) -> list[OutboxMessage]: ...
    async def mark_outbox_sent(self, outbox_id: UUID) -> None: ...
    async def mark_outbox_failed(self, outbox_id: UUID, error: str, now: datetime | None = None) -> None: ...

    async def consume_rate_limits(self, tenant_id: UUID, checks: Sequence[RateLimitCheck], now: datetime | None = None) -> RateLimitDecision: ...
    async def is_suppressed(self, tenant_id: UUID, kind: str, value: str) -> bool: ...
    async def add_suppression(self, tenant_id: UUID, kind: str, value: str, reason: str, source: str = "") -> None: ...
    async def write_audit(self, entry: NewAuditEntry) -> None: ...
    async def rollback_config_version(self, tenant_id: UUID, version_id: UUID, changed_by: str) -> bool: ...

    async def list_enabled_sources(self, tenant_id: UUID) -> list[GrowthSource]: ...
    async def update_source_run(self, tenant_id: UUID, source_id: UUID, last_run_at: datetime, last_error: str | None = None) -> None: ...
    async def upsert_lead(self, lead: NewSocialLead) -> tuple[SocialLead, bool]: ...
    async def get_lead(self, tenant_id: UUID, lead_id: UUID) -> SocialLead | None: ...
    async def list_leads(self, tenant_id: UUID, status: str | None = None, limit: int = 50) -> list[SocialLead]: ...
    async def update_lead_status(self, tenant_id: UUID, lead_id: UUID, expected_status: str, status: str, *, score: int | None = None, score_reasons: dict[str, Any] | None = None, model: str | None = None, prompt_version: str | None = None) -> bool: ...

    async def create_message(self, message: NewOutreachMessage) -> OutreachMessage: ...
    async def get_message(self, tenant_id: UUID, message_id: UUID) -> OutreachMessage | None: ...
    async def list_messages(self, tenant_id: UUID, status: str | None = None, limit: int = 50) -> list[OutreachMessage]: ...
    async def find_message_by_dedupe_key(self, tenant_id: UUID, dedupe_key: str) -> OutreachMessage | None: ...
    async def update_message_status(self, tenant_id: UUID, message_id: UUID, expected_status: str, status: str, *, sent_at: datetime | None = None, provider: str | None = None, provider_message_id: str | None = None, metadata_patch: dict[str, Any] | None = None) -> bool: ...
    async def create_version(self, version: NewOutreachVersion) -> OutreachVersion: ...
    async def get_latest_version(self, tenant_id: UUID, message_id: UUID) -> OutreachVersion | None: ...
    async def mark_version_approved(self, tenant_id: UUID, version_id: UUID, approved_by: str, approved_at: datetime) -> None: ...
    async def record_delivery(self, entry: NewDeliveryLog) -> None: ...
    async def count_followups(self, tenant_id: UUID, original_message_id: UUID) -> int: ...
    async def latest_sent_at(self, tenant_id: UUID, lead_id: UUID) -> datetime | None: ...

    async def create_approval_request(self, request: NewApprovalRequest) -> ApprovalRequest: ...
    async def get_approval_request(self, tenant_id: UUID, approval_id: str) -> ApprovalRequest | None: ...
    async def decide_approval(self, tenant_id: UUID, approval_id: str, status: str, decided_by: str, reason: str = "") -> bool: ...
    async def expire_pending_approvals(self, tenant_id: UUID, message_id: UUID) -> int: ...
    async def set_approval_external_id(self, tenant_id: UUID, approval_id: str, external_id: str) -> None: ...
```

Model fields (Pydantic v2; string statuses use `Literal` matching the migration CHECKs):

```python
class NewTask(BaseModel):
    tenant_id: UUID
    workspace_id: UUID
    pipeline: str
    task_type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str
    priority: int = 100
    run_after: datetime | None = None
    max_attempts: int = 5

class PipelineTask(NewTask):
    id: UUID
    status: Literal["queued", "running", "succeeded", "failed", "dead"]
    run_after: datetime
    locked_at: datetime | None = None
    locked_by: str | None = None
    attempts: int = 0
    last_error: str | None = None
    created_at: datetime
    updated_at: datetime

class NewOutboxMessage(BaseModel):
    tenant_id: UUID
    workspace_id: UUID
    topic: str
    payload: dict[str, Any]
    idempotency_key: str
    next_attempt_at: datetime | None = None

class OutboxMessage(NewOutboxMessage):
    id: UUID
    status: Literal["pending", "sending", "sent", "failed", "dead"]
    attempts: int = 0
    next_attempt_at: datetime
    last_error: str | None = None
    created_at: datetime
    updated_at: datetime

class ProviderConfig(BaseModel):
    id: UUID | None = None
    tenant_id: UUID
    capability: str
    provider: str
    priority: int = 100
    enabled: bool = True
    config: dict[str, Any] = Field(default_factory=dict)
    secret_ref: str | None = None
    config_schema_version: int = 1

class PromptTemplate(BaseModel):
    id: UUID
    tenant_id: UUID
    key: str
    module: str
    version: int
    template: str
    user_template: str
    output_schema: dict[str, Any]
    model_hint: str | None = None
    enabled: bool = True

class ScoringRubric(BaseModel):
    id: UUID
    tenant_id: UUID
    key: str
    version: int
    dimensions: list[dict[str, Any]]
    penalties: list[dict[str, Any]]
    thresholds: dict[str, int]
    enabled: bool = True

class RateLimitRule(BaseModel):
    tenant_id: UUID
    channel: str
    scope: Literal["global", "platform", "subreddit", "user"]
    scope_key: str = "*"
    window_seconds: int
    max_count: int
    enabled: bool = True

class RateLimitCheck(BaseModel):
    channel: str = "social"
    scope: str
    scope_key: str
    max_count: int
    window_seconds: int

class RateLimitDecision(BaseModel):
    allowed: bool
    exceeded_scope: str | None = None
    exceeded_scope_key: str | None = None
    retry_after_seconds: int = 0

class NewAuditEntry(BaseModel):
    tenant_id: UUID
    workspace_id: UUID | None = None
    actor_type: Literal["user", "service", "n8n", "system"]
    actor_id: str | None = None
    action: str
    entity_type: str
    entity_id: UUID | None = None
    before: dict[str, Any] | None = None
    after: dict[str, Any] | None = None

class GrowthSource(BaseModel):
    id: UUID
    tenant_id: UUID
    workspace_id: UUID
    source_type: str
    platform: str
    dedupe_key: str
    config: dict[str, Any] = Field(default_factory=dict)
    cadence_minutes: int = 30
    enabled: bool = True
    last_run_at: datetime | None = None
    last_error: str | None = None
    version: int = 1

class NewSocialLead(BaseModel):
    tenant_id: UUID
    workspace_id: UUID
    source_id: UUID | None = None
    platform: str
    platform_post_id: str
    title: str = ""
    body: str = ""
    author_public: str | None = None
    source_url: str
    published_at: datetime | None = None
    metrics: dict[str, Any] = Field(default_factory=dict)
    raw: dict[str, Any] | None = None
    subreddit: str | None = None
    subreddit_rules: dict[str, Any] = Field(default_factory=dict)
    dedupe_key: str

class SocialLead(NewSocialLead):
    id: UUID
    score: int | None = None
    score_reasons: dict[str, Any] | None = None
    model: str | None = None
    prompt_version: str | None = None
    status: str
    version: int = 1
    created_at: datetime
    updated_at: datetime

class NewOutreachMessage(BaseModel):
    tenant_id: UUID
    workspace_id: UUID
    channel: str
    provider: str | None = None
    lead_id: UUID | None = None
    user_id: UUID | None = None
    rule_key: str | None = None
    status: str
    scheduled_at: datetime | None = None
    dedupe_key: str
    metadata: dict[str, Any] = Field(default_factory=dict)

class OutreachMessage(NewOutreachMessage):
    id: UUID
    sent_at: datetime | None = None
    provider_message_id: str | None = None
    version: int = 1
    created_at: datetime
    updated_at: datetime

class NewOutreachVersion(BaseModel):
    tenant_id: UUID
    message_id: UUID
    version: int
    body_text: str
    subject: str | None = None
    cta_url: str | None = None
    model: str | None = None
    prompt_version: str | None = None
    risk_flags: list[str] = Field(default_factory=list)

class OutreachVersion(NewOutreachVersion):
    id: UUID
    approved_by: str | None = None
    approved_at: datetime | None = None
    created_at: datetime

class NewApprovalRequest(BaseModel):
    tenant_id: UUID
    workspace_id: UUID
    message_id: UUID
    approval_id: str
    provider: str = "feishu"
    external_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)

class ApprovalRequest(NewApprovalRequest):
    id: UUID
    status: Literal["pending", "approved", "rejected", "expired"]
    decided_by: str | None = None
    decided_at: datetime | None = None
    reason: str | None = None
    version: int = 1
    created_at: datetime
    updated_at: datetime

class NewDeliveryLog(BaseModel):
    tenant_id: UUID
    workspace_id: UUID
    message_id: UUID | None = None
    lead_id: UUID | None = None
    provider: str
    event_type: str
    payload: dict[str, Any] = Field(default_factory=dict)
```

- [ ] **Step 1: Write the failing Postgres tests**

```python
import os, uuid
from datetime import datetime, timezone, timedelta
import pytest
from growth_core.migrate import apply_migrations
from growth_core.repositories.postgres import PostgresGrowthRepository
from growth_core.schemas import NewTask

pytestmark = pytest.mark.integration

@pytest.mark.skipif(not os.getenv("GROWTH_TEST_DATABASE_URL"), reason="no test DB")
async def test_enqueue_task_is_idempotent():
    url = os.environ["GROWTH_TEST_DATABASE_URL"]
    await apply_migrations(url)
    repo = await PostgresGrowthRepository.connect(url)
    try:
        tenant_id, workspace_id = uuid.uuid4(), uuid.uuid4()
        await repo.ensure_tenant(tenant_id, workspace_id)
        task = NewTask(
            tenant_id=tenant_id, workspace_id=workspace_id,
            pipeline="social", task_type="social.ingest",
            payload={}, idempotency_key="ingest:1",
        )
        first = await repo.enqueue_task(task)
        second = await repo.enqueue_task(task)
        assert first == second
    finally:
        await repo.close()
```

Also write:
- `test_claim_task_returns_one_and_marks_running`
- `test_fail_task_backs_off_then_dead_letters`
- `test_outbox_idempotent_and_retry`
- `test_consume_rate_limits_is_atomic`
- `test_upsert_lead_deduplicates`

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd server && GROWTH_TEST_DATABASE_URL=postgresql://... python -m pytest tests/growth/test_repository_postgres.py -q`
Expected: FAIL because `PostgresGrowthRepository` is missing.

- [ ] **Step 3: Implement the repository**

`PostgresGrowthRepository` owns an `asyncpg.Pool`. `connect(database_url)` creates the pool; `close()` closes it. Use `pool.acquire()` and explicit transactions for multi-statement operations.

Key SQL:

Claim task:

```sql
update pipeline_runs
set status = 'running', locked_at = now(), locked_by = $1, updated_at = now()
where id = (
  select id from pipeline_runs
  where status = 'queued' and run_after <= $2::timestamptz
  order by priority, run_after, created_at
  for update skip locked
  limit 1
)
returning *;
```

Enqueue task idempotency:

```sql
insert into pipeline_runs
  (tenant_id, workspace_id, pipeline, task_type, payload, idempotency_key,
   priority, run_after, max_attempts)
values ($1,$2,$3,$4,$5,$6,$7,$8,$9)
on conflict (tenant_id, idempotency_key)
do update set updated_at = now()
returning id;
```

Fail task:

```sql
update pipeline_runs
set attempts = attempts + 1,
    status = case when attempts + 1 >= max_attempts then 'dead' else 'queued' end,
    run_after = case when attempts + 1 >= max_attempts then run_after
                     else $2::timestamptz + (60 * power(2, attempts)) * interval '1 second' end,
    last_error = $3,
    locked_at = null,
    locked_by = null,
    updated_at = now()
where id = $1;
```

Compute backoff in SQL from the row's current `attempts`; `fail_task` receives no attempt count, so it cannot do this in Python. Pass `now` as `$2`.

Rate limit consumption, inside one transaction:

```sql
insert into rate_limit_counters
  (tenant_id, channel, scope, scope_key, window_start, count)
values ($1,$2,$3,$4,$5,1)
on conflict (tenant_id, channel, scope, scope_key, window_start)
do update set count = rate_limit_counters.count + 1
where rate_limit_counters.count < $6
returning count;
```

If any check returns no row, raise an internal exception to roll back the transaction, then return `RateLimitDecision(allowed=False, exceeded_scope=..., exceeded_scope_key=..., retry_after_seconds=...)`. If all pass, return `RateLimitDecision(allowed=True)`.

`window_start = now - timedelta(seconds=int(now.timestamp()) % check.window_seconds)`; `retry_after_seconds = max(0, int((window_start + timedelta(seconds=check.window_seconds) - now).total_seconds()))`. Use `check.channel`, which defaults to `"social"`. Never use SQL `now()` where the method takes a `now` argument.

Upsert lead:

```sql
insert into social_leads (...)
values (...)
on conflict (tenant_id, dedupe_key) do nothing
returning *;
```

If no row is returned, select the existing row by `(tenant_id, dedupe_key)` and return `(lead, False)`.

`create_message`, `create_approval_request`, and `enqueue_outbox` use the same `on conflict (tenant_id, dedupe_key|approval_id|idempotency_key) do nothing returning *` pattern; if no row is returned, select the existing row and return it. This makes draft/card retries idempotent.

`claim_outbox(limit, now)` atomically marks up to `limit` rows with `status in ('pending','failed') and next_attempt_at <= $2` as `sending`, using `UPDATE ... WHERE id IN (SELECT id ... FOR UPDATE SKIP LOCKED LIMIT $1) RETURNING *`. `mark_outbox_failed` increments `attempts`, stores the error, and requeues with the same SQL-side backoff, setting `dead` when `attempts >= 5` (the table has no `max_attempts` column).

`count_followups(tenant_id, original_message_id)` counts `outreach_messages` rows whose `metadata->>'followup_of' = $2`. `get_prompt_template` and `get_scoring_rubric` with `version=None` select the highest enabled version.

Terminal writes are fenced. `complete_task` and `fail_task` update only `where id = $1 and status = 'running'` and, when `worker_id` is passed, `and locked_by = $n`; a stale worker whose task was reclaimed no-ops. `mark_outbox_sent` and `mark_outbox_failed` update only `where id = $1 and status = 'sending'`. `reclaim_stale_tasks` increments `attempts` and dead-letters when `attempts + 1 >= max_attempts`; otherwise it requeues with `locked_at/locked_by = null`, so a task that repeatedly kills its worker cannot loop forever. Treat `max_count <= 0` in a rate-limit check as fully blocked with no counter increment. Normalize every model datetime to timezone-aware UTC at the SQL boundary.

Status transitions always use `UPDATE ... WHERE tenant_id=$1 AND id=$2 AND status=$expected` and return `rowcount == 1`. If `rowcount == 0`, return `False`; callers treat it as a concurrency conflict.

`ensure_tenant(tenant_id, workspace_id)` is a test/helper method that inserts a tenant and workspace if missing; production uses the seed script. `add_source(source)` inserts one `growth_sources` row. `truncate_all_for_tests()` runs `TRUNCATE tenants CASCADE` and is test-only (never exposed by the API).

The `New*` models omit status columns that are NOT NULL in SQL, with one exception: `NewOutreachMessage.status` is required because Task 17 creates `draft_ready`, `rejected`, and `suppressed` messages. The repository injects the initial status in SQL only where the model omits it: `queued` for tasks, `pending` for outbox messages and approval requests, `discovered` for leads. It inserts the caller's status verbatim for messages. For tasks and leads, callers never pass status.

`rollback_config_version` reads `config_versions.snapshot`, updates the row in the whitelisted `table_name` (`prompt_templates`, `scoring_rubrics`, `provider_configs`) by `record_id`, and writes a new `config_versions` row recording the rollback. `rate_limit_rules` is excluded because it has no surrogate `id` column (composite primary key only), so `record_id` cannot address it. Unknown table names raise `ValueError`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd server && GROWTH_TEST_DATABASE_URL=postgresql://... python -m pytest tests/growth/test_repository_postgres.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add server/growth_core/schemas.py server/growth_core/repositories server/tests/growth/test_repository_postgres.py
git commit -m "feat: add postgres growth repository"
```

---

## Task 7: In-memory repository for deterministic tests

**Files:**
- Create: `server/tests/growth/fakes.py`
- Test: `server/tests/growth/test_repository_memory.py`

**Interfaces:**
- Produces `FakeGrowthRepository` implementing every `GrowthRepository` method with dict/list storage. Expose the stored lists as `repo.leads`, `repo.messages`, `repo.sources`, `repo.approvals`, `repo.outbox`, and `repo.tasks`; `ensure_tenant` is a no-op, `add_source` appends to `repo.sources`, and `close` is a no-op.
- Produces helpers:
  - `FakeGrowthRepository.tasks_for(idempotency_key_prefix: str) -> list[PipelineTask]` — matches `startswith`, because follow-up keys are compound (`followup:{original_id}:{message_id}`).
  - `FakeGrowthRepository.outbox_for(idempotency_key: str) -> list[OutboxMessage]`
  - `FakeGrowthRepository.set_rate_counter(tenant_id, channel, scope, scope_key, window_start, count)`

- [ ] **Step 1: Write the failing tests**

```python
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from growth_core.schemas import NewTask


async def test_fake_repository_task_idempotency(repo):
    tenant_id, workspace_id = uuid4(), uuid4()
    task = NewTask(
        tenant_id=tenant_id, workspace_id=workspace_id,
        pipeline="social", task_type="social.ingest", payload={},
        idempotency_key="ingest:1",
    )
    first = await repo.enqueue_task(task)
    second = await repo.enqueue_task(task)
    assert first == second
    assert len(repo.tasks_for("ingest:1")) == 1


async def test_fake_repository_rate_limit_is_all_or_nothing(repo, now):
    tenant_id = uuid4()
    from growth_core.schemas import RateLimitCheck
    checks = [
        RateLimitCheck(scope="global", scope_key="*", max_count=1, window_seconds=86400),
        RateLimitCheck(scope="platform", scope_key="reddit", max_count=1, window_seconds=86400),
    ]
    assert (await repo.consume_rate_limits(tenant_id, checks, now=now)).allowed
    decision = await repo.consume_rate_limits(tenant_id, checks, now=now)
    assert decision.allowed is False
    assert decision.exceeded_scope == "global"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd server && python -m pytest tests/growth/test_repository_memory.py -q`
Expected: FAIL because `fakes.py` does not exist.

- [ ] **Step 3: Implement `FakeGrowthRepository`**

Use dicts keyed by `UUID`. `enqueue_task` returns the existing id when `(tenant_id, idempotency_key)` is already present. `claim_task` returns the first queued task whose `run_after <= now`, marks it `running`, and increments `attempts` only on `fail_task`. `consume_rate_limits` first checks every counter at `window_start = now.replace(hour=0, minute=0, second=0, microsecond=0)`; if any would exceed, return a denied decision without incrementing any; otherwise increment all and return allowed.

Add `repo` fixture to `tests/growth/conftest.py`:

```python
@pytest.fixture
def repo():
    from tests.growth.fakes import FakeGrowthRepository
    return FakeGrowthRepository()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd server && python -m pytest tests/growth/test_repository_memory.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add server/tests/growth/fakes.py server/tests/growth/test_repository_memory.py server/tests/growth/conftest.py
git commit -m "test: add in-memory growth repository"
```

---

## Task 8: Core API authentication, health, and social API skeleton

**Files:**
- Create: `server/growth_core/api/__init__.py`
- Create: `server/growth_core/api/deps.py`
- Create: `server/growth_core/api/core.py`
- Create: `server/growth_social/api.py`
- Create: `server/growth_social/main.py`
- Test: `server/tests/growth/test_api_auth.py`

**Interfaces:**
- Produces:
  - `RequestContext` dataclass: `tenant_id: UUID`, `workspace_id: UUID`, `idempotency_key: str | None`
  - `async def require_service_token(request: Request) -> None`
  - `def get_context(request: Request) -> RequestContext`
  - `def create_social_app(*, settings: GrowthSettings, repo: GrowthRepository, adapters: AdapterRegistry | None = None, notifier: Notifier | None = None, llm: LLMClient | None = None) -> FastAPI`
- Produces endpoints:
  - `GET /healthz` → `{"status": "ok"}`
  - `POST /internal/v1/social/ingest` → `{"task_id": "<uuid>"}`
  - `POST /internal/v1/social/score` body `{"lead_id": "<uuid>"}` → `{"task_id": "<uuid>"}`
  - `POST /internal/v1/social/draft` body `{"lead_id": "<uuid>"}` → `{"task_id": "<uuid>"}`
  - `GET /api/growth/social/leads?status=...&limit=50`
  - `GET /api/growth/social/messages?status=...&limit=50`

- [ ] **Step 1: Write the failing tests**

```python
from fastapi.testclient import TestClient
from growth_core.config import GrowthSettings
from growth_social.main import create_social_app


def _settings() -> GrowthSettings:
    return GrowthSettings(
        database_url="postgresql://unused",
        service_token="service-token",
        tenant_id="00000000-0000-0000-0000-000000000001",
        workspace_id="00000000-0000-0000-0000-000000000002",
    )


def test_internal_endpoint_requires_service_token(repo):
    client = TestClient(create_social_app(settings=_settings(), repo=repo))
    response = client.post("/internal/v1/social/ingest", json={})
    assert response.status_code == 401


def test_internal_endpoint_enqueues_idempotent_ingest(repo):
    client = TestClient(create_social_app(settings=_settings(), repo=repo))
    headers = {
        "X-Service-Token": "service-token",
        "X-Tenant-Id": _settings().tenant_id,
        "X-Workspace-Id": _settings().workspace_id,
        "Idempotency-Key": "ingest:2026-11-15T09:00",
    }
    first = client.post("/internal/v1/social/ingest", json={}, headers=headers)
    second = client.post("/internal/v1/social/ingest", json={}, headers=headers)
    assert first.status_code == 200
    assert first.json()["task_id"] == second.json()["task_id"]


def test_health_is_public(repo):
    client = TestClient(create_social_app(settings=_settings(), repo=repo))
    assert client.get("/healthz").json() == {"status": "ok"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd server && python -m pytest tests/growth/test_api_auth.py -q`
Expected: FAIL because `create_social_app` does not exist.

- [ ] **Step 3: Implement auth, context, and routes**

`deps.py`:

```python
@dataclass(frozen=True)
class RequestContext:
    tenant_id: UUID
    workspace_id: UUID
    idempotency_key: str | None


async def require_service_token(request: Request) -> None:
    expected = request.app.state.settings.service_token
    supplied = request.headers.get("x-service-token", "")
    if not expected or not hmac.compare_digest(expected, supplied):
        raise HTTPException(status_code=401, detail="invalid service token")
```

`get_context` reads `X-Tenant-Id` and `X-Workspace-Id`; if absent, falls back to `settings.tenant_id` / `settings.workspace_id` for local single-tenant use. Both are parsed with `UUID(...)` and invalid values return `400 INVALID_TENANT_ID` / `400 INVALID_WORKSPACE_ID`. `Idempotency-Key` is optional for GET, required for the three POST task endpoints: missing key → `400 INVALID_IDEMPOTENCY_KEY`.

`core.py` exposes `/healthz`.

`growth_social/api.py` defines an `APIRouter` with the internal endpoints. Each task endpoint enqueues a `NewTask` with the context’s tenant/workspace and the request’s idempotency key:
- ingest: `pipeline="social"`, `task_type="social.ingest"`, payload `{}`.
- score: `pipeline="social"`, `task_type="social.score"`, payload `{"lead_id": str(body.lead_id)}`; idempotency key `score:{lead_id}` (ignore the header for this deterministic key).
- draft: `pipeline="social"`, `task_type="social.draft"`, payload `{"lead_id": str(body.lead_id)}`; idempotency key `draft:{lead_id}`.

`growth_social/main.py` defines `create_social_app(...)`, which stores `settings`, `repo`, `adapters`, `notifier`, `llm` on `app.state`, includes the core router and social router, and mounts no static frontend. Do **not** create a module-level `app` here; Task 21 adds the runtime entrypoint.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd server && python -m pytest tests/growth/test_api_auth.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add server/growth_core/api server/growth_social/api.py server/growth_social/main.py server/tests/growth/test_api_auth.py
git commit -m "feat: add growth internal API auth and task endpoints"
```

---

## Task 9: Feishu notifier, card signature verification, and fake notifier

**Files:**
- Create: `server/growth_core/adapters/__init__.py`
- Create: `server/growth_core/adapters/base.py` (`AdapterHealth` plus the adapter exception hierarchy)
- Create: `server/growth_core/adapters/feishu.py`
- Create: `server/growth_core/services/feishu_signature.py`
- Modify: `server/tests/growth/fakes.py` (add `FakeNotifier`)
- Test: `server/tests/growth/test_feishu.py`

**Interfaces:**
- Produces `FeishuNotifier(*, app_id: str, app_secret: str, base_url: str = "https://open.feishu.cn", client: httpx.AsyncClient | None = None)` with:
  - `async def send_card(self, chat_id: str, card: dict[str, Any]) -> str` (returns Feishu `message_id`)
  - `async def health(self) -> AdapterHealth`
- Produces `AdapterHealth(name: str, status: str, detail: str = "")` plus `AdapterError`, `ProviderNotConfigured`, `ProviderAuthError`, `ProviderRateLimited`, `ProviderTimeout`, `ProviderUnavailable`, and `ProviderBadOutput` in `growth_core/adapters/base.py` (Task 10 reuses these, it does not redefine them).
- Produces:
  - `def verify_feishu_signature(headers: Mapping[str, str], body: bytes, encrypt_key: str) -> bool`
  - `def verify_feishu_token(payload: dict[str, Any], expected_token: str) -> bool`
  - `class FakeNotifier` in `tests/growth/fakes.py` with `cards: list[dict]`

- [ ] **Step 1: Write the failing tests**

```python
import hashlib
import hmac

from growth_core.services.feishu_signature import verify_feishu_signature


def test_feishu_signature_matches_official_formula():
    ts, nonce, key, body = "1700000000", "abc", "encrypt-key", b'{"hello":"world"}'
    expected = hashlib.sha256(
        (ts + nonce + key).encode("utf-8") + body
    ).hexdigest()
    headers = {
        "x-lark-request-timestamp": ts,
        "x-lark-request-nonce": nonce,
        "x-lark-signature": expected,
    }
    assert verify_feishu_signature(headers, body, key) is True


def test_feishu_signature_rejects_tampering():
    headers = {
        "x-lark-request-timestamp": "1700000000",
        "x-lark-request-nonce": "abc",
        "x-lark-signature": "bad",
    }
    assert verify_feishu_signature(headers, b"{}", "encrypt-key") is False


async def test_feishu_notifier_posts_interactive_card():
    import httpx
    from growth_core.adapters.feishu import FeishuNotifier

    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.url.path.endswith("/tenant_access_token/internal"):
            return httpx.Response(200, json={"tenant_access_token": "t", "expire": 7200})
        return httpx.Response(200, json={"code": 0, "data": {"message_id": "om_1"}})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    notifier = FeishuNotifier(
        app_id="app", app_secret="secret", client=client,
        base_url="https://open.feishu.cn",
    )
    message_id = await notifier.send_card("oc_1", {"config": {}})
    assert message_id == "om_1"
    assert any("im/v1/messages" in str(call.url) for call in calls)
    await client.aclose()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd server && python -m pytest tests/growth/test_feishu.py -q`
Expected: FAIL because the modules do not exist.

- [ ] **Step 3: Implement notifier and signature helpers**

`FeishuNotifier` caches the tenant access token until `expire - 60` seconds. Token endpoint:

```text
POST {base_url}/open-apis/auth/v3/tenant_access_token/internal
{"app_id": ..., "app_secret": ...}
```

Send endpoint:

```text
POST {base_url}/open-apis/im/v1/messages?receive_id_type=chat_id
Authorization: Bearer <token>
{"receive_id": chat_id, "msg_type": "interactive", "content": json.dumps(card)}
```

Map Feishu errors: `99991663`/`99991664`/HTTP 401 → `ProviderAuthError`; HTTP 429 or `code` in rate-limit range → `ProviderRateLimited`; HTTP 5xx/timeout → `ProviderUnavailable`. Never log the app secret or token.

`verify_feishu_signature` computes `sha256((timestamp + nonce + encrypt_key).encode("utf-8") + body).hexdigest()` and compares with `hmac.compare_digest`.

`verify_feishu_token(payload, expected)` reads `payload.get("header", {}).get("token")` and compares in constant time.

Add `FakeNotifier` to `tests/growth/fakes.py`:

```python
class FakeNotifier:
    def __init__(self) -> None:
        self.cards: list[dict] = []
        self.calls: list[tuple[str, dict]] = []

    async def send_card(self, chat_id: str, card: dict) -> str:
        self.calls.append((chat_id, card))
        self.cards.append(card)
        return f"fake-{len(self.cards)}"

    async def health(self):
        from growth_core.adapters.base import AdapterHealth
        return AdapterHealth(name="fake", status="ready")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd server && python -m pytest tests/growth/test_feishu.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add server/growth_core/adapters/feishu.py server/growth_core/services/feishu_signature.py server/tests/growth/test_feishu.py server/tests/growth/fakes.py
git commit -m "feat: add feishu notifier and callback verification"
```

---

## Task 10: Adapter protocols, registry, and secret resolution

**Files:**
- Create: `server/growth_core/adapters/registry.py`
- Modify: `server/growth_core/adapters/base.py`
- Modify: `server/growth_core/adapters/feishu.py`
- Test: `server/tests/growth/test_registry.py`

**Interfaces:**
- Produces:
  - `AdapterError`, `ProviderNotConfigured`, `ProviderAuthError`, `ProviderRateLimited`, `ProviderTimeout`, `ProviderUnavailable`, `ProviderBadOutput` (created in Task 9; import and reuse, do not redefine)
  - `AdapterHealth(name: str, status: str, detail: str = "")` (already created in Task 9; extend the file, do not redefine it)
  - `RawPost` dataclass
  - `SourceAdapter` protocol: `name`, `capabilities: dict[str, Any]`, `async fetch(source: GrowthSource) -> list[RawPost]`, `async health() -> AdapterHealth`, `def validate_config(self) -> None`
  - `Notifier` protocol: `async send_card(chat_id, card) -> str`, `async health() -> AdapterHealth`
  - `LLMClient` protocol: `async complete_json(*, system: str, user: str, schema: type[BaseModel], model: str | None = None) -> BaseModel`
  - `SecretResolver` protocol + `EnvSecretResolver`
  - `register_adapter(capability: str, provider: str)` decorator
  - `AdapterRegistry(configs: Sequence[ProviderConfig], secrets: SecretResolver)`
- Produces methods `AdapterRegistry.source(provider: str)`, `.notifier()`, `.llm()`.

- [ ] **Step 1: Write the failing tests**

```python
import pytest
from growth_core.adapters.base import ProviderNotConfigured, SourceAdapter
from growth_core.adapters.registry import AdapterRegistry, EnvSecretResolver, register_adapter
from growth_core.schemas import ProviderConfig


class DummySource:
    name = "dummy"
    def __init__(self, config, secrets):
        self.config = config
    async def fetch(self, source):
        return []
    async def health(self):
        return None


def test_registry_resolves_configured_source(monkeypatch):
    register_adapter("social_source", "dummy")(DummySource)
    config = ProviderConfig(
        tenant_id="00000000-0000-0000-0000-000000000001",
        capability="social_source", provider="dummy",
        priority=10, enabled=True, config={}, secret_ref=None,
    )
    registry = AdapterRegistry([config], EnvSecretResolver())
    adapter = registry.source("dummy")
    assert adapter.name == "dummy"


def test_registry_missing_provider_raises():
    registry = AdapterRegistry([], EnvSecretResolver())
    with pytest.raises(ProviderNotConfigured):
        registry.source("reddit")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd server && python -m pytest tests/growth/test_registry.py -q`
Expected: FAIL because the modules do not exist.

- [ ] **Step 3: Implement protocols, registry, and secret resolver**

`AdapterRegistry` stores `{(capability, provider): factory}` from the decorator and `{(capability, provider): ProviderConfig}` from the constructor. A **factory is always a callable `factory(config: ProviderConfig, secrets: SecretResolver) -> adapter`**. `source`, `notifier`, and `llm` call it with `(config, secrets)`. Missing config or factory → `ProviderNotConfigured(f"PROVIDER_NOT_CONFIGURED: {capability}/{provider}")`.

Adapters with keyword-only constructors register a small factory function that delegates to their classmethod, e.g.:

```python
@register_adapter("social_source", "reddit")
def _reddit_factory(config, secrets):
    return RedditAdapter.from_config(config, secrets)
```

Registering a class directly is allowed only when its constructor signature is `(config, secrets)`.

`EnvSecretResolver.get(ref)` returns `os.environ[ref]`; missing raises `ProviderNotConfigured` naming the env var, never the value.

Then update `feishu.py`: import `register_adapter`, add a `@register_adapter("notifier", "feishu")` factory `_feishu_factory(config, secrets)` returning `FeishuNotifier.from_config(config, secrets)`, and implement `from_config` reading `chat_id` from `config.config.get("chat_id_env", "GROWTH_FEISHU_CHAT_ID")` via `os.environ` and the app secret via `secrets.get(config.secret_ref)`. The app ID comes from `GROWTH_FEISHU_APP_ID` (or `config.config["app_id_env"]`).

`RawPost`:

```python
@dataclass(frozen=True)
class RawPost:
    platform: str
    platform_post_id: str
    title: str
    body: str
    author_public: str | None
    source_url: str
    published_at: datetime | None
    metrics: dict[str, Any]
    subreddit: str | None
    raw: dict[str, Any]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd server && python -m pytest tests/growth/test_registry.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add server/growth_core/adapters server/tests/growth/test_registry.py
git commit -m "feat: add growth adapter registry"
```

---

## Task 11: Worker loop and outbox dispatcher

**Files:**
- Create: `server/growth_core/services/__init__.py`
- Create: `server/growth_core/services/worker.py`
- Create: `server/growth_core/services/outbox.py`
- Test: `server/tests/growth/test_worker_outbox.py`

**Interfaces:**
- Produces:
  - `TaskHandler = Callable[[PipelineTask], Awaitable[None]]`
  - `TaskRouter.register(task_type: str, handler: TaskHandler) -> None`
  - `async TaskRouter.handle(task: PipelineTask) -> None`
  - `async def run_once(repo, router, *, worker_id: str, now: datetime | None = None) -> bool`
  - `async def run_forever(repo, router, *, worker_id: str, poll_seconds: float = 2.0, stop: asyncio.Event | None = None) -> None`
  - `async def dispatch_outbox(repo, notifier, *, limit: int = 10, now: datetime | None = None) -> int`

- [ ] **Step 1: Write the failing tests**

```python
from uuid import uuid4
from growth_core.schemas import NewTask, NewOutboxMessage


async def test_run_once_claims_and_completes(repo, now):
    from growth_core.services.worker import TaskRouter, run_once

    seen = []

    async def demo(task):
        seen.append(task)

    router = TaskRouter()
    router.register("demo", demo)
    tenant_id, workspace_id = uuid4(), uuid4()
    await repo.enqueue_task(NewTask(
        tenant_id=tenant_id, workspace_id=workspace_id,
        pipeline="social", task_type="demo", payload={},
        idempotency_key="demo:1",
    ))
    assert await run_once(repo, router, worker_id="w1", now=now) is True
    assert len(seen) == 1
    assert await run_once(repo, router, worker_id="w1", now=now) is False


async def test_handler_failure_is_recorded(repo, now):
    from growth_core.services.worker import TaskRouter, run_once

    async def boom(task):
        raise RuntimeError("boom")

    router = TaskRouter()
    router.register("demo", boom)
    tenant_id, workspace_id = uuid4(), uuid4()
    await repo.enqueue_task(NewTask(
        tenant_id=tenant_id, workspace_id=workspace_id,
        pipeline="social", task_type="demo", payload={},
        idempotency_key="demo:2", max_attempts=2,
    ))
    await run_once(repo, router, worker_id="w1", now=now)
    task = repo.tasks_for("demo:2")[0]
    assert task.status == "queued"
    assert task.attempts == 1
    assert "boom" in task.last_error
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd server && python -m pytest tests/growth/test_worker_outbox.py -q`
Expected: FAIL because the worker module does not exist.

- [ ] **Step 3: Implement worker and outbox**

`run_once` claims one task; if none, returns `False`. It dispatches by `task.task_type`; on success calls `repo.complete_task(task.id, task.locked_by)` and returns `True`; on exception calls `repo.fail_task(task.id, f"{type(exc).__name__}: {exc}", worker_id=task.locked_by)` and returns `True`. A task that dead-letters is also returned as claimed; the outbox/Feishu alert is a later task.

`run_forever` loops `run_once`, sleeps `poll_seconds` when idle, and exits when `stop.is_set()`.

`dispatch_outbox` claims up to `limit` messages. For `topic == "feishu.card"`, it reads `payload["chat_id"]`, `payload["card"]`, and `payload["approval_id"]`; sends via notifier; on success calls `repo.set_approval_external_id(tenant_id, approval_id, external_id)` and `repo.mark_outbox_sent(id)`; on exception calls `repo.mark_outbox_failed(id, str(exc))`. Unknown topics are marked dead via `mark_outbox_failed` with `unsupported topic`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd server && python -m pytest tests/growth/test_worker_outbox.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add server/growth_core/services server/tests/growth/test_worker_outbox.py
git commit -m "feat: add growth worker and outbox dispatcher"
```

---

## Task 12: Reddit adapter

**Files:**
- Create: `server/growth_social/adapters/__init__.py`
- Create: `server/growth_social/adapters/reddit.py`
- Test: `server/tests/growth/test_reddit_adapter.py`

**Interfaces:**
- Produces `RedditAdapter(*, client: httpx.AsyncClient, user_agent: str, base_url: str = "https://www.reddit.com")`
- `name = "reddit"`, `async fetch(source: GrowthSource) -> list[RawPost]`, `async health() -> AdapterHealth`
- `@classmethod def from_config(cls, config: ProviderConfig, secrets: SecretResolver) -> RedditAdapter`
- Registered with `@register_adapter("social_source", "reddit")` on a module-level factory `_reddit_factory(config, secrets) -> RedditAdapter` that delegates to `from_config`.
- Reads `source.config`: `subreddit: str`, `keywords: list[str]` (optional), `limit: int` (default 25).

- [ ] **Step 1: Write the failing tests**

```python
import httpx
from growth_core.schemas import GrowthSource
from growth_social.adapters.reddit import RedditAdapter


def _source(config):
    from uuid import uuid4
    return GrowthSource(
        id=uuid4(), tenant_id=uuid4(), workspace_id=uuid4(),
        source_type="reddit", platform="reddit", dedupe_key="reddit:r/saas",
        config=config, cadence_minutes=30, enabled=True,
    )


async def test_reddit_fetches_and_filters_keywords():
    payload = {"data": {"children": [
        {"data": {"id": "a1", "title": "How do I track SaaS churn?", "selftext": "manual spreadsheet",
                  "author": "u/x", "permalink": "/r/saas/comments/a1/x/", "created_utc": 1700000000,
                  "score": 3, "num_comments": 2, "subreddit": "saas", "stickied": False}},
        {"data": {"id": "a2", "title": "Weekly promo", "selftext": "",
                  "author": "u/y", "permalink": "/r/saas/comments/a2/y/", "created_utc": 1700000000,
                  "score": 0, "num_comments": 0, "subreddit": "saas", "stickied": False}},
    ]}}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["user-agent"] == "test-agent"
        return httpx.Response(200, json=payload)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = RedditAdapter(client=client, user_agent="test-agent")
    posts = await adapter.fetch(_source({"subreddit": "saas", "keywords": ["churn"], "limit": 10}))
    assert len(posts) == 1
    assert posts[0].platform_post_id == "a1"
    assert posts[0].source_url == "https://www.reddit.com/r/saas/comments/a1/x/"
    await client.aclose()
```

Also test:
- `test_reddit_429_raises_rate_limited`
- `test_reddit_skips_stickied_posts`
- `test_reddit_missing_subreddit_raises_bad_config`

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd server && python -m pytest tests/growth/test_reddit_adapter.py -q`
Expected: FAIL because `reddit.py` does not exist.

- [ ] **Step 3: Implement the adapter**

Register the `_reddit_factory` function (not the class) with `@register_adapter("social_source", "reddit")`. `from_config` reads `config.config.get("base_url", "https://www.reddit.com")`, resolves the user agent via `secrets.get(config.secret_ref)` when `secret_ref` is present, and creates an `httpx.AsyncClient(timeout=20)`.

GET `{base_url}/r/{subreddit}/new.json?limit={limit}` with `User-Agent`. For each child:
- Skip `stickied` and non-dict data.
- Combine `title` and `selftext`; if `keywords` is non-empty and none appear case-insensitively, skip.
- `platform_post_id = data["id"]`.
- `source_url = f"https://www.reddit.com{data['permalink']}"`.
- `published_at = datetime.fromtimestamp(data["created_utc"], tz=timezone.utc)`.
- `metrics = {"score": data.get("score", 0), "comments": data.get("num_comments", 0)}`.
- `subreddit = data.get("subreddit")`.
- `raw = data`.

Error mapping:
- 429 → `ProviderRateLimited("PROVIDER_RATE_LIMITED", "reddit rate limited", retry_after_seconds=...)`
- 401/403 → `ProviderAuthError`
- 5xx/timeout → `ProviderUnavailable`
- 404 → `ProviderNotConfigured` with a hint that the subreddit may not exist.

`health()` returns `AdapterHealth(name="reddit", status="ready")` without a network call in v1; the ingestion task reports real fetch failures through `update_source_run`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd server && python -m pytest tests/growth/test_reddit_adapter.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add server/growth_social/adapters server/tests/growth/test_reddit_adapter.py
git commit -m "feat: add reddit source adapter"
```

---

## Task 13: Hacker News adapter

**Files:**
- Create: `server/growth_social/adapters/hackernews.py`
- Test: `server/tests/growth/test_hackernews_adapter.py`

**Interfaces:**
- Produces `HackerNewsAdapter(*, client: httpx.AsyncClient, base_url: str = "https://hn.algolia.com")`
- `name = "hackernews"`, `async fetch(source: GrowthSource) -> list[RawPost]`, `async health() -> AdapterHealth`
- `@classmethod def from_config(cls, config: ProviderConfig, secrets: SecretResolver) -> HackerNewsAdapter`
- Registered with `@register_adapter("social_source", "hackernews")` on a module-level factory `_hackernews_factory(config, secrets) -> HackerNewsAdapter` that delegates to `from_config`.
- Reads `source.config`: `query: str`, `limit: int` (default 25).

- [ ] **Step 1: Write the failing test**

```python
import httpx
from growth_core.schemas import GrowthSource
from growth_social.adapters.hackernews import HackerNewsAdapter


async def test_hackernews_maps_algolia_hits():
    payload = {"hits": [{
        "objectID": "123",
        "title": "Ask HN: How do you track customer churn?",
        "story_text": "We use a spreadsheet and it is painful.",
        "author": "pg",
        "url": "https://example.com/post",
        "created_at_i": 1700000000,
        "points": 42,
        "num_comments": 7,
    }]}

    def handler(request: httpx.Request) -> httpx.Response:
        assert "query=churn" in str(request.url)
        return httpx.Response(200, json=payload)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = HackerNewsAdapter(client=client)
    source = GrowthSource(
        id=__import__("uuid").uuid4(), tenant_id=__import__("uuid").uuid4(),
        workspace_id=__import__("uuid").uuid4(), source_type="hackernews",
        platform="hackernews", dedupe_key="hn:churn",
        config={"query": "churn", "limit": 10}, cadence_minutes=30, enabled=True,
    )
    posts = await adapter.fetch(source)
    assert posts[0].platform_post_id == "123"
    assert posts[0].source_url == "https://example.com/post"
    assert posts[0].metrics["points"] == 42
    await client.aclose()
```

Also test:
- Missing `url` falls back to `https://news.ycombinator.com/item?id=123`.
- 429 → `ProviderRateLimited`.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd server && python -m pytest tests/growth/test_hackernews_adapter.py -q`
Expected: FAIL because `hackernews.py` does not exist.

- [ ] **Step 3: Implement the adapter**

Register the `_hackernews_factory` function with `@register_adapter("social_source", "hackernews")`. `from_config` reads `config.config.get("base_url", "https://hn.algolia.com")` and creates an `httpx.AsyncClient(timeout=20)`.

GET `{base_url}/api/v1/search_by_date` with params `query`, `tags="story"`, `hitsPerPage=limit`. Map:
- `platform_post_id = str(hit["objectID"])`
- `title = hit.get("title") or ""`
- `body = hit.get("story_text") or hit.get("comment_text") or ""`
- `author_public = hit.get("author")`
- `source_url = hit.get("url") or f"https://news.ycombinator.com/item?id={platform_post_id}"`
- `published_at = datetime.fromtimestamp(hit["created_at_i"], tz=timezone.utc)`
- `metrics = {"points": hit.get("points", 0), "comments": hit.get("num_comments", 0)}`
- `subreddit = None`
- `raw = hit`

Error mapping mirrors Reddit. `health()` is network-free in v1.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd server && python -m pytest tests/growth/test_hackernews_adapter.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add server/growth_social/adapters/hackernews.py server/tests/growth/test_hackernews_adapter.py
git commit -m "feat: add hacker news source adapter"
```

---

## Task 14: Ingestion service with dedupe and score-task enqueueing

**Files:**
- Create: `server/growth_social/services/__init__.py`
- Create: `server/growth_social/services/ingest.py`
- Test: `server/tests/growth/test_ingest.py`

**Interfaces:**
- Produces:
  - `async def ingest_social(repo: GrowthRepository, adapters: Mapping[str, SourceAdapter], *, tenant_id: UUID, workspace_id: UUID, now: datetime | None = None) -> IngestResult`
  - `SourceError(source_id: UUID, code: str, message: str)` dataclass
  - `IngestResult(created: int, duplicates: int, errors: list[SourceError])`
- Lead dedupe key: `sha256(f"{platform}:{platform_post_id}")`.

- [ ] **Step 1: Write the failing tests**

```python
from uuid import uuid4
from growth_core.adapters.base import RawPost
from growth_core.schemas import GrowthSource
from growth_social.services.ingest import ingest_social


class FakeReddit:
    name = "reddit"
    def __init__(self, posts):
        self.posts = posts
    async def fetch(self, source):
        return self.posts
    async def health(self):
        return None


async def test_ingest_creates_one_lead_and_one_score_task(repo, now):
    tenant_id, workspace_id = uuid4(), uuid4()
    source = GrowthSource(
        id=uuid4(), tenant_id=tenant_id, workspace_id=workspace_id,
        source_type="reddit", platform="reddit", dedupe_key="reddit:r/saas",
        config={"subreddit": "saas"}, cadence_minutes=30, enabled=True,
    )
    await repo.add_source(source)
    post = RawPost(
        platform="reddit", platform_post_id="a1", title="Churn pain",
        body="We track churn manually", author_public="u/x",
        source_url="https://www.reddit.com/r/saas/comments/a1/x/",
        published_at=now, metrics={"score": 3}, subreddit="saas",
        raw={"id": "a1"},
    )
    result = await ingest_social(
        repo, {"reddit": FakeReddit([post, post])},
        tenant_id=tenant_id, workspace_id=workspace_id, now=now,
    )
    assert result.created == 1
    assert result.duplicates == 1
    assert len(repo.tasks_for(f"score:{repo.leads[0].id}")) == 1


async def test_ingest_continues_after_one_source_error(repo, now):
    # one source raises ProviderUnavailable, a second returns a post;
    # result.errors has one entry and the second lead exists.
    ...
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd server && python -m pytest tests/growth/test_ingest.py -q`
Expected: FAIL because `ingest.py` does not exist.

- [ ] **Step 3: Implement ingestion**

For each enabled source:
- Resolve `adapter = adapters[source.source_type]`; missing adapter → error entry, continue.
- `posts = await adapter.fetch(source)`.
- For each post, build `NewSocialLead` with `subreddit_rules` from `source.config.get("subreddit_rules", {})`, `dedupe_key = sha256(...)`.
- `lead, created = await repo.upsert_lead(new_lead)`.
- If `created`, enqueue `NewTask(pipeline="social", task_type="social.score", payload={"lead_id": str(lead.id)}, idempotency_key=f"score:{lead.id}")`.
- Call `repo.update_source_run(...)` on success or with `last_error` on failure.
- Catch `AdapterError` per source, append `SourceError(source_id, code, message)`, and continue.

`add_source` is part of `GrowthRepository` (Task 6) and already implemented by `FakeGrowthRepository` (Task 7); do not add a second version.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd server && python -m pytest tests/growth/test_ingest.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add server/growth_social/services/ingest.py server/tests/growth/test_ingest.py server/tests/growth/fakes.py
git commit -m "feat: add social ingestion with dedupe"
```

---

## Task 15: OpenAI-compatible LLM client and JSON parsing

**Files:**
- Create: `server/growth_core/adapters/llm.py`
- Test: `server/tests/growth/test_llm.py`

**Interfaces:**
- Produces:
  - `def extract_json(text: str) -> dict[str, Any]`
  - `class OpenAICompatibleLLM` with `async complete_json(*, system: str, user: str, schema: type[BaseModel], model: str | None = None) -> BaseModel`
  - Constructor: `OpenAICompatibleLLM(*, api_key: str, model: str, base_url: str | None = None, timeout: float = 60.0, client: Any | None = None)`
  - `@classmethod def from_config(cls, config: ProviderConfig, secrets: SecretResolver) -> OpenAICompatibleLLM`
  - Registered with `@register_adapter("llm", "openai_compatible")` on a module-level factory `_llm_factory(config, secrets)` that delegates to `from_config`.

- [ ] **Step 1: Write the failing tests**

```python
import pytest
from pydantic import BaseModel
from growth_core.adapters.llm import OpenAICompatibleLLM, extract_json


class Score(BaseModel):
    value: int


def test_extract_json_handles_code_fences():
    assert extract_json('```json\n{"value": 7}\n```') == {"value": 7}


class StubCompletions:
    async def create(self, **kwargs):
        from types import SimpleNamespace
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content='{"value": 7}'))]
        )


async def test_complete_json_validates_schema():
    stub = SimpleNamespace(chat=SimpleNamespace(completions=StubCompletions()))
    llm = OpenAICompatibleLLM(api_key="k", model="m", client=stub)
    result = await llm.complete_json(system="s", user="u", schema=Score)
    assert isinstance(result, Score)
    assert result.value == 7


async def test_bad_json_raises_provider_bad_output():
    class Bad:
        async def create(self, **kwargs):
            from types import SimpleNamespace
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="not json"))]
            )
    stub = SimpleNamespace(chat=SimpleNamespace(completions=Bad()))
    llm = OpenAICompatibleLLM(api_key="k", model="m", client=stub)
    with pytest.raises(Exception, match="PROVIDER_BAD_OUTPUT"):
        await llm.complete_json(system="s", user="u", schema=Score)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd server && python -m pytest tests/growth/test_llm.py -q`
Expected: FAIL because `llm.py` does not exist.

- [ ] **Step 3: Implement the client**

Register `_llm_factory` with `@register_adapter("llm", "openai_compatible")`. `from_config` reads `base_url` from `config.config` and `model` from `config.config.get("model", "")` (the seeded config has no model; scoring and drafting pass their own model on every call), resolves `api_key` via `secrets.get(config.secret_ref)`, and returns the client.

`extract_json` strips whitespace, strips a leading ```/```json fence and trailing ```, then `json.loads`; on failure raise `ProviderBadOutput`.

`OpenAICompatibleLLM.complete_json`:
- If `client is None`, create `AsyncOpenAI(api_key=api_key, base_url=base_url, timeout=timeout)`.
- Call `chat.completions.create(model=model or self.model, messages=[{"role":"system","content":system},{"role":"user","content":user}], response_format={"type":"json_object"}, temperature=0)`.
- Extract content; `data = extract_json(content)`; `return schema.model_validate(data)`.
- Any `ValidationError`, JSON error, timeout, or SDK exception → `ProviderBadOutput` / `ProviderUnavailable` with a stable code. Do not echo the raw prompt content in the error.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd server && python -m pytest tests/growth/test_llm.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add server/growth_core/adapters/llm.py server/tests/growth/test_llm.py
git commit -m "feat: add openai-compatible llm client"
```

---

## Task 16: Intent scoring with server-side weighted scorecard

**Files:**
- Create: `server/growth_social/schemas.py`
- Create: `server/growth_social/services/scoring.py`
- Create: `server/tests/growth/golden/social_posts.jsonl`
- Test: `server/tests/growth/test_scoring.py`
- Test: `server/tests/growth/test_prompt_regression.py`

**Interfaces:**
- Produces in `growth_social/schemas.py`:

```python
class IntentDimensionDraft(BaseModel):
    dimension_id: str
    score: int = Field(ge=0, le=10)
    rationale: str = ""

class IntentPenaltyDraft(BaseModel):
    code: str
    points: int = Field(le=0)
    rationale: str = ""

class IntentScoreDraft(BaseModel):
    dimensions: list[IntentDimensionDraft]
    penalties: list[IntentPenaltyDraft] = Field(default_factory=list)
    summary: str = ""

class IntentScore(BaseModel):
    score: int = Field(ge=0, le=100)
    status: Literal["qualified", "watch", "dropped"]
    dimensions: list[IntentDimensionDraft]
    penalties: list[IntentPenaltyDraft]
    summary: str = ""
```

- Produces `async def score_lead(repo, llm, *, tenant_id: UUID, lead_id: UUID, model: str = "", now: datetime | None = None) -> IntentScore`
- Algorithm: `round(sum(d.score * weight / 10) + sum(p.points))`, clamped to 0–100; thresholds from the rubric.

- [ ] **Step 1: Write the failing tests**

```python
async def test_score_qualified_enqueues_draft(repo, now):
    # seed rubric + prompt + lead; FakeLLM returns all 10s, no penalties
    score = await score_lead(repo, fake_llm, tenant_id=tenant_id, lead_id=lead.id, now=now)
    assert score.score == 100
    assert score.status == "qualified"
    assert len(repo.tasks_for(f"draft:{lead.id}")) == 1


async def test_score_watch_does_not_draft(repo, now):
    # all dimensions 7 -> base 70; status watch; no draft task
    ...


async def test_penalty_can_downgrade_below_threshold(repo, now):
    # dimensions 10/10/10/10/10 -> 100, penalty ad -50 -> 50 -> dropped
    ...


async def test_missing_dimension_is_bad_output(repo, now):
    # FakeLLM omits reply_safety; expect ProviderBadOutput and lead unchanged
    ...


# test_prompt_regression.py
async def test_golden_set_precision_at_threshold():
    # 50 labeled posts in golden/social_posts.jsonl, each with expected_status
    # and a fixture of model dimensions; run the server scorecard over them and
    # assert precision(qualified) >= 0.8 at threshold 80.
    ...
```

`golden/social_posts.jsonl` has 50 lines, each `{"id","platform","title","body","age_days","expected_status","dimensions","penalties"}`. Write 25 qualified and 25 non-qualified synthetic posts across Reddit/HN, including ads, already-solved, stale, and duplicate cases. The deterministic regression test uses the stored `dimensions`/`penalties` (no API); a second test with `@pytest.mark.skipif(not os.getenv("GROWTH_TEST_LLM"), ...)` calls the real LLM on the same 50 posts and asserts the same precision floor.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd server && python -m pytest tests/growth/test_scoring.py -q`
Expected: FAIL because `scoring.py` does not exist.

- [ ] **Step 3: Implement scoring**

Load `lead`, `rubric = await repo.get_scoring_rubric(tenant_id, "social_intent")`, and `prompt = await repo.get_prompt_template(tenant_id, "social_intent")`. Render the user prompt from `prompt.user_template` with `string.Template.safe_substitute(platform=..., community=..., age_days=..., title=..., body=...)`; pass `prompt.template` as the system prompt.

Call `llm.complete_json(system=..., user=..., schema=IntentScoreDraft, model=model or None)`. Validate that the returned dimensions exactly match the rubric ids; missing or unknown id → `ProviderBadOutput`. The scoring handler passes `settings.llm_scoring_model` (Task 21), keeping scoring on the cheap model.

Compute the score. `status` = `qualified` if `score >= rubric.thresholds["qualified"]`; `watch` if `>= rubric.thresholds["watch"]`; else `dropped`.

Update the lead with `repo.update_lead_status(tenant_id, lead_id, expected_status=lead.status, status=status, score=score, score_reasons=..., model=llm.model, prompt_version=str(prompt.version))`. If the update returns `False`, re-read and return the current lead’s score without enqueueing a duplicate task.

If `status == "qualified"`, enqueue `NewTask(pipeline="social", task_type="social.draft", payload={"lead_id": str(lead_id)}, idempotency_key=f"draft:{lead_id}")`.

If the lead is already scored (`lead.score is not None`), return `IntentScore(score=lead.score, status=lead.status if lead.status in {"qualified","watch","dropped"} else "watch", dimensions=[], penalties=[], summary="")` without calling the LLM, and do not enqueue a duplicate draft task.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd server && python -m pytest tests/growth/test_scoring.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add server/growth_social/schemas.py server/growth_social/services/scoring.py server/tests/growth/test_scoring.py server/tests/growth/test_prompt_regression.py server/tests/growth/golden
git commit -m "feat: add server-side intent scoring"
```

---

## Task 17: Link policy, reply drafting, and Feishu approval card

**Files:**
- Create: `server/growth_social/services/prompts.py`
- Create: `server/growth_social/services/link_policy.py`
- Create: `server/growth_social/services/cards.py`
- Create: `server/growth_social/services/drafting.py`
- Modify: `server/growth_social/schemas.py` (add `ReplyDraft`)
- Test: `server/tests/growth/test_link_policy.py`
- Test: `server/tests/growth/test_drafting.py`

**Interfaces:**
- Produces:
  - `LinkPolicyConfig(allowed_domain: str, utm_medium: str = "reply", require_disclosure: bool = True)`
  - `LinkPolicyResult(ok: bool, link_url: str | None, violations: list[str], manual_only: bool = False)`
  - `def build_utm_url(base_url: str, link_path: str, *, lead_id: str, platform: str) -> str`
  - `def validate_link_policy(text: str, config: LinkPolicyConfig, *, subreddit_allows_links: bool = True) -> LinkPolicyResult`
  - `ReplyDraft` Pydantic model in `growth_social/schemas.py`: `body_markdown: str` (must contain exactly one `{{LINK}}`), `link_path: str`, `risk_flags: list[str]`.
  - `async def draft_reply(repo, llm, notifier, *, tenant_id, workspace_id, lead_id, settings: GrowthSettings, now=None) -> OutreachMessage`
  - `def build_approval_card(*, approval_id: str, message: OutreachMessage, lead: SocialLead, version: OutreachVersion, score: IntentScore, link_policy: LinkPolicyResult) -> dict[str, Any]`

- [ ] **Step 1: Write the failing link-policy tests**

```python
from growth_social.services.link_policy import LinkPolicyConfig, validate_link_policy

CFG = LinkPolicyConfig(allowed_domain="example.com")

def test_valid_deep_link_with_utm_and_disclosure():
    text = (
        "That manual spreadsheet gets painful. I built Example, and this checklist "
        "helps: https://example.com/guides/churn?utm_source=reddit&utm_medium=reply&utm_campaign=lead-1"
    )
    result = validate_link_policy(text, CFG)
    assert result.ok is True
    assert result.link_url.startswith("https://example.com/guides/churn")


def test_two_links_rejected():
    text = "I built Example. https://example.com/a?utm_source=reddit&utm_medium=reply&utm_campaign=x https://example.com/b?utm_source=reddit&utm_medium=reply&utm_campaign=x"
    assert validate_link_policy(text, CFG).ok is False


def test_shortener_rejected():
    text = "I built Example. https://bit.ly/abc"
    assert "SHORTENER" in " ".join(validate_link_policy(text, CFG).violations)


def test_homepage_rejected():
    text = "I built Example. https://example.com/?utm_source=reddit&utm_medium=reply&utm_campaign=x"
    assert "NOT_DEEP_LINK" in validate_link_policy(text, CFG).violations


def test_missing_utm_rejected():
    text = "I built Example. https://example.com/guides/churn"
    assert "MISSING_UTM" in validate_link_policy(text, CFG).violations


def test_missing_disclosure_rejected():
    text = "This checklist helps: https://example.com/guides/churn?utm_source=reddit&utm_medium=reply&utm_campaign=x"
    assert "MISSING_DISCLOSURE" in validate_link_policy(text, CFG).violations


def test_no_link_subreddit_marks_manual_only():
    text = "I built Example. https://example.com/guides/churn?utm_source=reddit&utm_medium=reply&utm_campaign=x"
    result = validate_link_policy(text, CFG, subreddit_allows_links=False)
    assert result.ok is False
    assert result.manual_only is True


def test_link_before_value_rejected():
    text = "https://example.com/guides/churn?utm_source=reddit&utm_medium=reply&utm_campaign=x I built Example."
    assert "LINK_TOO_EARLY" in validate_link_policy(text, CFG).violations
```

- [ ] **Step 2: Write the failing drafting tests**

```python
async def test_draft_creates_version_approval_and_card(repo, fake_llm, fake_notifier, now):
    # lead is draft-eligible; fake_llm returns a valid ReplyDraft
    message = await draft_reply(...)
    assert message.status == "draft_ready"
    assert await repo.get_latest_version(tenant_id, message.id) is not None
    assert len(fake_notifier.cards) == 1


async def test_missing_placeholder_is_rejected(repo, fake_llm, fake_notifier, now):
    # ReplyDraft body has no {{LINK}}
    message = await draft_reply(...)
    assert message.status == "rejected"
    assert fake_notifier.cards == []


async def test_no_link_subreddit_is_suppressed(repo, fake_llm, fake_notifier, now):
    # lead.subreddit_rules = {"self_promotion_allowed": False}
    message = await draft_reply(...)
    assert message.status == "suppressed"
    assert fake_notifier.cards == []
```

- [ ] **Step 3: Implement link policy and drafting**

`build_utm_url` joins `base_url.rstrip("/") + link_path`, parses it, and sets `utm_source=UTM_SOURCES.get(platform, platform)` (mapping `reddit` → `reddit`, `hackernews` → `hn`), `utm_medium=reply`, `utm_campaign=lead_id` using `urllib.parse.urlencode`. It must preserve existing query params and reject `link_path` that starts with `http://`, `https://`, `//`, or contains `..`.

`validate_link_policy`:
- Extract URLs with `re.findall(r"https?://[^\s)\]>]+", text)`.
- Exactly one URL; 0 → `NO_LINK`, >1 → `MULTIPLE_LINKS`.
- Parse hostname; reject hosts in `SHORTENER_HOSTS` (`bit.ly`, `t.co`, `goo.gl`, `tinyurl.com`, `ow.ly`, `buff.ly`, `rebrand.ly`, `cutt.ly`, `is.gd`, `rb.gy`).
- Host must equal allowed domain or end with `.{allowed_domain}`.
- Path must not be empty or `/`.
- Query must contain `utm_source`, `utm_medium=reply`, non-empty `utm_campaign`.
- Text must contain a disclosure phrase case-insensitively: `i built`, `i work on`, `our team built`, `we built`, `i'm building`, `i am building`.
- Link position: the disclosure phrase must appear **before** the URL, and the URL must not appear in the first sentence (before the first `. ` or newline). Otherwise add `LINK_TOO_EARLY`.
- If `subreddit_allows_links=False`, set `manual_only=True` and add `SUBREDDIT_NO_LINKS`; drafting converts that to `suppressed`.

`draft_reply`:
- Before calling the LLM, check `existing = await repo.find_message_by_dedupe_key(tenant_id, f"draft:{lead_id}")`; if it exists, return it after ensuring its approval request and Feishu outbox row exist (use deterministic `approval_id = f"{existing.id}:v{latest.version}"` and outbox key `feishu:{approval_id}`). This makes worker retries safe even if the previous attempt crashed between writes.
- Load lead and `prompt = repo.get_prompt_template(tenant_id, "social_reply")`; pass `prompt.template` as the system prompt.
- Build `score = IntentScore(score=lead.score or 0, status=lead.status if lead.status in {"qualified","watch","dropped"} else "watch", dimensions=[], penalties=[], summary="")` for the approval card.
- Render the user prompt from `prompt.user_template` with `string.Template.safe_substitute`.
- Call `llm.complete_json(..., schema=ReplyDraft, model=settings.llm_drafting_model or None)` so drafting uses the stronger model.
- Require exactly one `{{LINK}}`; otherwise create a `rejected` message with `metadata.policy_violations=["PLACEHOLDER_COUNT"]` and audit, return it.
- `url = build_utm_url(settings.product_url, draft.link_path, lead_id=str(lead.id), platform=lead.platform)`.
- `final_text = draft.body_markdown.replace("{{LINK}}", url)`.
- `subreddit_allows_links = lead.subreddit_rules.get("self_promotion_allowed", True)`.
- `policy = validate_link_policy(final_text, LinkPolicyConfig(allowed_domain=settings.product_domain), subreddit_allows_links=subreddit_allows_links)`.
- If `policy.manual_only`: create message `status="suppressed"` with `dedupe_key=f"draft:{lead.id}"`, metadata `{"policy_violations": policy.violations}`, audit; return.
- If not `policy.ok`: create message `status="rejected"` with `dedupe_key=f"draft:{lead.id}"`, metadata `{"policy_violations": policy.violations}`, audit; return.
- Otherwise create `OutreachMessage` with `channel="social"`, `provider=lead.platform`, `lead_id=lead.id`, `workspace_id=workspace_id`, `status="draft_ready"`, `dedupe_key=f"draft:{lead.id}"`, metadata `{"subreddit": lead.subreddit, "has_link": True, "platform": lead.platform, "draft_version": 1}`.
- Create `OutreachVersion(version=1, workspace_id=workspace_id, body_text=final_text, cta_url=url, model=llm.model, prompt_version=str(prompt.version), risk_flags=draft.risk_flags)`.
- Create `ApprovalRequest(approval_id=f"{message.id}:v1", workspace_id=workspace_id, provider="feishu", payload={"chat_id": settings.feishu_chat_id})`.
- Build the card and enqueue `NewOutboxMessage(topic="feishu.card", payload={"chat_id": settings.feishu_chat_id, "card": card, "approval_id": approval.approval_id}, idempotency_key=f"feishu:{approval.approval_id}")`.
- Update lead to `draft_ready` with `expected_status="qualified"`.
- Write audit entries for `social.draft_created` and `social.draft_rejected`/`social.draft_suppressed`.

`build_approval_card` uses Feishu interactive card JSON:
- Header title: `"Social reply approval"`.
- Fields: platform/community, post title, source URL, score, score summary, risk flags, subreddit rules result, draft text, final link.
- Actions: `approve`, `edit`, `reject`, `later`; each `value` includes `{"approval_id": approval_id, "action": "<action>"}`.
- Never include secrets or full raw provider payloads.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd server && python -m pytest tests/growth/test_link_policy.py tests/growth/test_drafting.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add server/growth_social/services/prompts.py server/growth_social/services/link_policy.py server/growth_social/services/cards.py server/growth_social/services/drafting.py server/growth_social/schemas.py server/tests/growth/test_link_policy.py server/tests/growth/test_drafting.py
git commit -m "feat: add reply drafting and link policy"
```

---

## Task 18: Feishu approval callback and revision flow

**Files:**
- Create: `server/growth_social/services/approval.py`
- Modify: `server/growth_social/api.py`
- Test: `server/tests/growth/test_approval.py`

**Interfaces:**
- Produces:
  - `FeishuAction(approval_id: str, action: Literal["approve","reject","edit","later"], operator: str | None)`
  - `def parse_feishu_action(payload: dict[str, Any]) -> FeishuAction`
  - `ApprovalResult(status: Literal["approved","rejected","pending","already_decided","not_found"], message_id: UUID | None = None)`
  - `async def handle_approval(repo, *, tenant_id: UUID, action: FeishuAction, now: datetime | None = None) -> ApprovalResult`
  - `POST /internal/v1/approvals/callback` (Feishu signature/token verified; no service-token header)
  - `POST /api/growth/social/messages/{message_id}/revise` body `{"body_markdown": "...", "operator": "..."}`

- [ ] **Step 1: Write the failing tests**

```python
async def test_approve_transitions_message_and_version(repo, now):
    result = await handle_approval(
        repo, tenant_id=tenant_id,
        action=FeishuAction(approval_id=approval_id, action="approve", operator="ou_1"),
        now=now,
    )
    assert result.status == "approved"
    message = await repo.get_message(tenant_id, message_id)
    assert message.status == "approved"
    version = await repo.get_latest_version(tenant_id, message_id)
    assert version.approved_by == "ou_1"


async def test_duplicate_approve_is_idempotent(repo, now):
    first = await handle_approval(...)
    second = await handle_approval(...)
    assert first.status == "approved"
    assert second.status == "already_decided"


async def test_reject_transitions_to_rejected(repo, now):
    result = await handle_approval(..., action="reject")
    assert result.status == "rejected"


async def test_revise_creates_new_version_and_new_approval(repo, now):
    # POST revise with a valid body; old version remains, version 2 exists,
    # message is draft_ready, a new approval request and card exist.
    ...
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd server && python -m pytest tests/growth/test_approval.py -q`
Expected: FAIL because `approval.py` does not exist.

- [ ] **Step 3: Implement approval and revision**

`parse_feishu_action` supports both current and legacy payload shapes:
- Current: `payload["event"]["action"]["value"]` and `payload["event"]["operator"]["operator_id"]["open_id"]`.
- Legacy: `payload["action"]["value"]` and `payload["open_id"]`.
- Missing `approval_id` or action → `ValueError("INVALID_FEISHU_ACTION")`.

`handle_approval`:
- Load approval by `(tenant_id, approval_id)`. Missing → `not_found`.
- If approval.status is already `approved`/`rejected`/`expired`:
  - Same action → `already_decided`.
  - Different action or expired → `already_decided` (never overwrite a human decision).
- `approve`: `repo.decide_approval(status="approved", decided_by=operator)`; `repo.update_message_status(expected_status="draft_ready", status="approved")`; `repo.mark_version_approved(...)`; audit `social.approved`.
- `reject`: `decide_approval(status="rejected", reason="feishu_reject")`; `update_message_status(expected_status="draft_ready", status="rejected")`; audit.
- `edit`: no state change; return `pending` with a message telling the operator to use the Admin UI.
- `later`: no state change; return `pending`.

The callback endpoint (`/internal/v1/approvals/callback`) is **exempt from `X-Service-Token`** because Feishu cannot send it; it is authenticated only by the signature/verification-token checks below. Every other `/internal/v1/*` endpoint keeps the service token.

The callback endpoint:
- Reads raw body bytes.
- If `settings.feishu_encrypt_key`: verify signature; invalid → 403.
- Else: parse JSON and verify `payload["header"]["token"]` with `verify_feishu_token`; invalid → 403.
- Handles Feishu URL verification: if `payload.get("type") == "url_verification"`, return `{"challenge": payload["challenge"]}`.
- Calls `handle_approval`; returns `{"toast": {"type": "success", "content": "..."}}` or an error toast. Always 200 for valid Feishu events to avoid retries; unknown approval returns a toast, not 500.

Revision endpoint:
- Load message; allow only `draft_ready` or `approved`.
- Validate the new text with `validate_link_policy` using the settings domain and the lead’s subreddit rules. Invalid → 422 with `violations`.
- Create a new `OutreachVersion` with `version = latest.version + 1` and `workspace_id`.
- `await repo.expire_pending_approvals(tenant_id, message_id)` so old Feishu cards cannot approve the new version.
- Reset message to `draft_ready` (from `approved` or `draft_ready`), update metadata `draft_version = new_version`, create a new `ApprovalRequest(approval_id=f"{message.id}:v{new_version}")`, enqueue a new Feishu card outbox message with key `feishu:{approval_id}`.
- Preserve all previous versions and approval records.
- Audit `social.revised` with operator and version.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd server && python -m pytest tests/growth/test_approval.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add server/growth_social/services/approval.py server/growth_social/api.py server/tests/growth/test_approval.py
git commit -m "feat: add feishu approval callback and revision"
```

---

## Task 19: Manual send tracking with send-time rate limits and suppression

**Files:**
- Create: `server/growth_core/services/ratelimit.py`
- Create: `server/growth_social/services/sending.py`
- Modify: `server/growth_social/api.py`
- Test: `server/tests/growth/test_sending.py`

**Interfaces:**
- Produces:
  - `RateLimitContext(tenant_id: UUID, channel: str, platform: str, subreddit: str | None, has_link: bool, now: datetime)`
  - `async def check_send_allowed(repo, ctx: RateLimitContext) -> RateLimitDecision`
  - `class SendBlocked(Exception)` with `code: str`, `detail: str`
  - `async def mark_sent(repo, *, tenant_id: UUID, workspace_id: UUID, message_id: UUID, sent_at: datetime | None = None, channel: str = "manual", now: datetime | None = None) -> OutreachMessage`
  - `POST /api/growth/social/messages/{message_id}/sent` body `{"sent_at": "<iso8601 optional>", "channel": "manual"}`

- [ ] **Step 1: Write the failing tests**

```python
import pytest
from growth_social.services.sending import SendBlocked, mark_sent


async def test_mark_sent_transitions_and_schedules_followup(repo, now):
    message = await mark_sent(
        repo, tenant_id=tenant_id, workspace_id=workspace_id,
        message_id=approved_message.id, now=now,
    )
    assert message.status == "sent"
    assert message.sent_at == now
    assert len(repo.tasks_for(f"followup:{message.id}")) == 1


async def test_mark_sent_requires_approved_status(repo, now):
    with pytest.raises(SendBlocked, match="INVALID_TRANSITION"):
        await mark_sent(repo, ..., message_id=draft_message.id, now=now)


async def test_mark_sent_blocks_suppressed_platform_user(repo, now):
    await repo.add_suppression(tenant_id, "platform_user", f"{platform}:{author}", "manual")
    with pytest.raises(SendBlocked, match="SUPPRESSED"):
        await mark_sent(repo, ..., message_id=approved_message.id, now=now)


async def test_mark_sent_blocks_reddit_daily_limit(repo, now):
    # seed 5 sent reddit messages today, then attempt the 6th
    with pytest.raises(SendBlocked, match="RATE_LIMITED"):
        await mark_sent(repo, ..., message_id=approved_message.id, now=now)


async def test_mark_sent_blocks_global_daily_limit(repo, now):
    # seed 50 sent social messages today
    ...


async def test_mark_sent_blocks_subreddit_link_limit(repo, now):
    # seed 2 sent messages with the same subreddit and has_link=true today
    ...
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd server && python -m pytest tests/growth/test_sending.py -q`
Expected: FAIL because `sending.py` does not exist.

- [ ] **Step 3: Implement rate-limit policy and send tracking**

`check_send_allowed` loads `repo.list_rate_limit_rules(tenant_id, channel="social")`. Build checks:
- Always add `global/*` with its rule’s `max_count` and `window_seconds`.
- If a platform rule exists for `ctx.platform` or `scope_key="*"`, add `platform/{platform}`.
- If `ctx.platform == "reddit"` and `ctx.subreddit` and `ctx.has_link`, add `subreddit/{subreddit}` using the `subreddit/*` rule.

Use the first matching rule per scope; if a rule is disabled, skip it. Call `repo.consume_rate_limits(tenant_id, checks, now=ctx.now)`.

`mark_sent`:
- Load message; missing → `SendBlocked("NOT_FOUND")`.
- Require `message.status == "approved"`; otherwise `SendBlocked("INVALID_TRANSITION")`.
- Load lead. If this is the **original** message (`message.metadata.get("followup_of")` is absent) and `lead.status` is `sent`/`replied`/`converted`, raise `SendBlocked("ALREADY_CONTACTED")`. Follow-up messages are allowed while the lead is `sent`; if a follow-up and `lead.status` is `replied`/`converted`/`suppressed`/`rejected`, raise `SendBlocked("LEAD_CLOSED")`.
- If `lead.author_public`, check `repo.is_suppressed(tenant_id, "platform_user", f"{lead.platform}:{lead.author_public}")`; if true, set message `suppressed` (expected `approved`), audit, raise `SendBlocked("SUPPRESSED")`.
- Build `RateLimitContext(tenant_id, "social", lead.platform, lead.subreddit, has_link=True, now=now or sent_at or utcnow())`.
- If denied, write audit `social.send_blocked` with the exceeded scope, set the message to `suppressed` (expected `approved`), and raise `SendBlocked("RATE_LIMITED", f"{scope}:{key}")`. The operator must create a new draft after the window; an over-limit message never stays approved.
- Otherwise load `latest = await repo.get_latest_version(tenant_id, message_id)` and `repo.update_message_status(expected_status="approved", status="sent", sent_at=..., provider=lead.platform, metadata_patch={"channel": channel, "subreddit": lead.subreddit, "has_link": True, "draft_version": latest.version if latest else 0})`; if `False`, reload and raise `SendBlocked("CONCURRENT_UPDATE")`.
- `repo.update_lead_status(expected_status=lead.status, status="sent")`; ignore a concurrency conflict if the lead is already `sent`.
- `await repo.expire_pending_approvals(tenant_id, message_id)` so a delayed Feishu tap cannot re-approve a sent message.
- Write `delivery_log` via `repo.record_delivery(...)` (declared in Task 6): event `sent`, provider `lead.platform`, payload `{"channel": channel}`.
- Enqueue follow-up check: `original_id = message.metadata.get("followup_of", str(message.id))`; `NewTask(pipeline="social", task_type="social.followup_check", payload={"original_message_id": original_id}, idempotency_key=f"followup:{original_id}:{message.id}", run_after=(sent_at + timedelta(days=1)))`.
- Write audit `social.sent`.
- Return the updated message.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd server && python -m pytest tests/growth/test_sending.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add server/growth_core/services/ratelimit.py server/growth_social/services/sending.py server/growth_social/api.py server/growth_core/repositories server/tests/growth/test_sending.py
git commit -m "feat: add manual send tracking and send-time limits"
```

---

## Task 20: Bounded follow-up generation

**Files:**
- Create: `server/growth_social/services/followup.py`
- Test: `server/tests/growth/test_followup.py`

**Interfaces:**
- Produces:
  - `async def process_followup_check(repo, llm, notifier, *, tenant_id, workspace_id, original_message_id: UUID, settings: GrowthSettings, now: datetime | None = None) -> OutreachMessage | None`
  - `FollowUpDecision` enum-like strings: `"created"`, `"rescheduled"`, `"stopped"`.

- [ ] **Step 1: Write the failing tests**

```python
async def test_followup_reschedules_until_one_day(repo, now):
    result = await process_followup_check(..., now=now + timedelta(hours=23))
    assert result is None
    assert len(repo.tasks_for(f"followup:{original.id}")) == 2  # original + reschedule


async def test_followup_creates_one_draft_after_one_day(repo, fake_llm, fake_notifier, now):
    message = await process_followup_check(..., now=now + timedelta(hours=24))
    assert message.metadata["followup_of"] == str(original.id)
    assert message.metadata["followup_index"] == 1
    assert message.status == "draft_ready"
    assert len(fake_notifier.cards) == 1


async def test_followup_stops_after_three(repo, fake_llm, fake_notifier, now):
    # three existing follow-ups; fourth check returns None and creates no card
    ...


async def test_followup_stops_when_lead_replied(repo, fake_llm, fake_notifier, now):
    await repo.update_lead_status(..., status="replied")
    assert await process_followup_check(...) is None
    assert fake_notifier.cards == []


async def test_followup_stops_when_suppressed(repo, fake_llm, fake_notifier, now):
    await repo.add_suppression(tenant_id, "platform_user", f"{platform}:{author}", "negative_reply")
    assert await process_followup_check(...) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd server && python -m pytest tests/growth/test_followup.py -q`
Expected: FAIL because `followup.py` does not exist.

- [ ] **Step 3: Implement follow-up logic**

`process_followup_check`:
- Load original message. If not `sent`, stop.
- Load lead. If lead status is `replied`, `converted`, `suppressed`, or `rejected`, stop.
- If the lead’s author is suppressed, stop.
- `count = await repo.count_followups(tenant_id, original_message_id)`; if `count >= settings.followup_max_total`, stop.
- `last = await repo.latest_sent_at(tenant_id, lead.id)`; if `now - last < timedelta(hours=settings.followup_min_interval_hours)`, enqueue the same check with `run_after = last + 24h` and a new idempotency key `followup:{original_id}:retry:{int(now.timestamp())}`; return `None`.
- Load `prompt = repo.get_prompt_template(tenant_id, "social_followup")` and the previous version text. Pass `prompt.template` as the system prompt and render `prompt.user_template` with `string.Template.safe_substitute`.
- Call `llm.complete_json(..., schema=ReplyDraft)` with `$title`, `$body`, `$previous_reply`, `$followup_index`, `$product_name`.
- Apply the same placeholder/link-policy validation as Task 17. Invalid → create `rejected` message and audit, return it (do not send another follow-up).
- Create a new `OutreachMessage` with `dedupe_key=f"followup:{original_message_id}:{count + 1}"` and `metadata={"followup_of": str(original_message_id), "followup_index": count + 1, "subreddit": lead.subreddit, "has_link": True, "draft_version": 1}`; create version 1; create approval request with `approval_id=f"{message.id}:v1"`; enqueue Feishu card.
- Set `run_after` not here; the next check is scheduled when the human marks this follow-up sent. `mark_sent` reads `metadata.followup_of` and enqueues the next check.
- Audit `social.followup_created`.

Duplicate prevention: before creating, check `repo.find_message_by_dedupe_key(tenant_id, f"followup:{original_message_id}:{count + 1}")` (declared in Task 6). If it exists, return it without creating a new card.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd server && python -m pytest tests/growth/test_followup.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add server/growth_social/services/followup.py server/growth_core/repositories server/tests/growth/test_followup.py
git commit -m "feat: add bounded social follow-up"
```

---

## Task 21: Wire task handlers/work entrypoints and prove the end-to-end flow

**Files:**
- Create: `server/growth_social/handlers.py`
- Create: `server/growth_social/worker.py`
- Create: `server/growth_social/asgi.py`
- Create: `server/growth_core/worker.py`
- Modify: `server/growth_social/main.py`
- Test: `server/tests/growth/test_social_e2e.py`

**Interfaces:**
- Produces `def build_social_router(*, repo, adapters, notifier, llm, settings) -> TaskRouter` registering:
  - `social.ingest` → `ingest_social`
  - `social.score` → `score_lead`
  - `social.draft` → `draft_reply`
  - `social.followup_check` → `process_followup_check`
- Produces `async def build_social_adapters(repo, settings) -> AdapterRegistry` that loads `social_source` provider configs and enabled sources, constructs the registry, and returns it.
- Produces `python -m growth_social.worker` entrypoint that loads settings, creates a Postgres pool/repository, builds adapters/notifier/llm, runs `run_forever` and `dispatch_outbox` in one event loop.
- Produces `python -m growth_social.main` serving the FastAPI app by delegating to `growth_social.asgi:app`.
- `growth_social/asgi.py` defines the module-level `app = create_social_app(...)` from environment; tests never import it.

- [ ] **Step 1: Write the failing end-to-end test**

```python
from datetime import timedelta
from growth_social.services.approval import FeishuAction, handle_approval
from growth_social.services.sending import mark_sent
from growth_social.handlers import build_social_router
from growth_core.services.worker import run_once


async def test_social_flow_from_post_to_followup(repo, fake_notifier, now):
    # 1. seed tenant/workspace, sources, prompt templates, rubric, provider configs
    #    fake Reddit returns one high-intent post
    # 2. run social.ingest -> one lead + one score task
    # 3. run social.score -> qualified + one draft task
    # 4. run social.draft -> draft_ready + one Feishu card + one approval request
    # 5. handle_approval(approve) -> message approved
    # 6. mark_sent -> message sent, delivery log, follow-up task
    # 7. process_followup_check at +24h -> follow-up draft_ready + second card
    # 8. assert the follow-up also has exactly one link and disclosure
    router = build_social_router(
        repo=repo, adapters={"reddit": fake_reddit}, notifier=fake_notifier,
        llm=fake_llm, settings=settings,
    )
    await run_once(repo, router, worker_id="w1", now=now)
    ...
    assert fake_notifier.cards[0]["header"]["title"]["content"] == "Social reply approval"
    assert "https://example.com/" in fake_notifier.cards[0]["elements"][-1]["text"]["content"]
    assert message.status == "sent"
    assert followup.metadata["followup_index"] == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd server && python -m pytest tests/growth/test_social_e2e.py -q`
Expected: FAIL because handlers/worker wiring does not exist.

- [ ] **Step 3: Implement handlers and entrypoints**

`handlers.py` registers the four task types. Payload keys: `social.ingest` none; `social.score` and `social.draft` use `lead_id`; `social.followup_check` uses `original_message_id`. The score handler passes `model=settings.llm_scoring_model`; the draft handler relies on `draft_reply` using `settings.llm_drafting_model`. Handler exceptions propagate to `run_once`, which records them.

`growth_core/worker.py` is the generic loop entrypoint placeholder; `growth_social/worker.py` is the real composition root:
- `settings = GrowthSettings.from_env()`
- `repo = await PostgresGrowthRepository.connect(settings.database_url)`
- `configs = await repo.list_provider_configs(settings.tenant_id, "social_source")`; `registry = AdapterRegistry(configs, EnvSecretResolver())`; `sources = await repo.list_enabled_sources(settings.tenant_id)`; `adapters = {s.source_type: registry.source(s.source_type) for s in sources if s.enabled}`. `build_social_adapters` returns `(registry, adapters)`.
- `notifier = registry.notifier()`; `llm = registry.llm()`
- `router = build_social_router(repo=repo, adapters=adapters, notifier=notifier, llm=llm, settings=settings)`
- loop: `await run_once(...)`; `await dispatch_outbox(repo, notifier)`; sleep when idle.

`growth_social/asgi.py` builds the same composition root and exposes `app = create_social_app(...)`. `growth_social/main.py` runs `uvicorn growth_social.asgi:app`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd server && python -m pytest tests/growth/test_social_e2e.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add server/growth_social/handlers.py server/growth_social/worker.py server/growth_social/asgi.py server/growth_social/main.py server/growth_core/worker.py server/tests/growth/test_social_e2e.py
git commit -m "feat: wire social pipeline end to end"
```

---

## Task 22: Postgres integration tests for queue, outbox, rate limits, and RLS

**Files:**
- Create: `server/tests/growth/test_postgres_integration.py`
- Modify: `server/tests/growth/conftest.py`
- Modify: `server/growth_core/repositories/postgres.py`
- Test: `server/tests/growth/test_postgres_integration.py`

**Interfaces:**
- Produces fixture `pg_repo` gated by `GROWTH_TEST_DATABASE_URL`; it applies migrations, truncates, and yields a connected repository. No separate `truncate_growth` fixture.

- [ ] **Step 1: Write the failing tests**

```python
import os
import pytest

pytestmark = pytest.mark.integration

@pytest.mark.skipif(not os.getenv("GROWTH_TEST_DATABASE_URL"), reason="no test DB")
async def test_two_workers_claim_distinct_tasks(pg_repo, now):
    # enqueue two tasks, open two repository instances/connections,
    # claim concurrently, assert ids differ and both are running
    ...


@pytest.mark.skipif(not os.getenv("GROWTH_TEST_DATABASE_URL"), reason="no test DB")
async def test_rate_limit_is_atomic_under_concurrency(pg_repo, now):
    # two concurrent consume calls for max_count=1; exactly one is allowed
    ...


@pytest.mark.skipif(not os.getenv("GROWTH_TEST_DATABASE_URL"), reason="no test DB")
async def test_rls_hides_other_tenant(pg_repo):
    # create tenant A and B with one lead each; set role growth_test_app and
    # request.jwt.claims tenant A; select count(*) from social_leads == 1
    ...
```

- [ ] **Step 2: Run tests to verify they fail or skip**

Run: `cd server && GROWTH_TEST_DATABASE_URL=postgresql://... python -m pytest tests/growth/test_postgres_integration.py -q`
Expected: FAIL because fixtures/repository behavior are incomplete.

- [ ] **Step 3: Implement fixtures and RLS test**

`conftest.py`:

```python
@pytest.fixture
async def pg_repo():
    url = os.environ.get("GROWTH_TEST_DATABASE_URL")
    if not url:
        pytest.skip("GROWTH_TEST_DATABASE_URL is not set")
    from growth_core.migrate import apply_migrations
    from growth_core.repositories.postgres import PostgresGrowthRepository
    await apply_migrations(url)
    repo = await PostgresGrowthRepository.connect(url)
    await repo.truncate_all_for_tests()
    yield repo
    await repo.close()
```

Add `truncate_all_for_tests()` to the Postgres repository: `TRUNCATE tenants CASCADE` (and lookup tables if needed). This is test-only and must not be exposed by the API.

RLS test setup:
- As the test superuser, insert tenant A and B and one lead each.
- `create role growth_test_app nologin` if missing; `grant usage on schema public`; `grant select on social_leads`.
- `set role growth_test_app; select set_config('request.jwt.claims', '{"tenant_id":"<A>"}', true);`
- `select count(*) from social_leads` must return 1.
- `reset role`.

Also test:
- `test_fail_task_backoff_and_dead_letter`
- `test_outbox_retry_marks_sent`
- `test_upsert_lead_dedupes`
- `test_claim_task_skip_locked_with_two_connections`
- `test_config_rollback_restores_snapshot` (write a `prompt_templates` row, record a `config_versions` snapshot with an older template, roll back, assert the template text is restored and a new version row exists)

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd server && GROWTH_TEST_DATABASE_URL=postgresql://... python -m pytest tests/growth/test_postgres_integration.py -q`
Expected: PASS. If no URL is set, all tests skip.

- [ ] **Step 5: Commit**

```bash
git add server/tests/growth/test_postgres_integration.py server/tests/growth/conftest.py server/growth_core/repositories/postgres.py
git commit -m "test: add postgres concurrency and RLS coverage"
```

---

## Task 23: Runbook, environment example, and tracking-matrix update

**Files:**
- Create: `server/.env.growth.example`
- Create: `server/docs/growth-runbook.md`
- Modify: `server/README.md`
- Modify: `ideas_pool/GROWTH_AGENT_TRACKING.md`

- [ ] **Step 1: Write `.env.growth.example`**

Include every `GrowthSettings` env var, with placeholders only:

```text
GROWTH_DATABASE_URL=postgresql://user:password@host:5432/postgres
GROWTH_SERVICE_TOKEN=change-me
GROWTH_TENANT_ID=00000000-0000-0000-0000-000000000001
GROWTH_WORKSPACE_ID=00000000-0000-0000-0000-000000000002
GROWTH_FEISHU_APP_ID=
GROWTH_FEISHU_APP_SECRET=
GROWTH_FEISHU_VERIFICATION_TOKEN=
GROWTH_FEISHU_ENCRYPT_KEY=
GROWTH_FEISHU_CHAT_ID=
GROWTH_FEISHU_BASE_URL=https://open.feishu.cn
GROWTH_REDDIT_USER_AGENT=growth-agent/0.1 (by /u/yourname)
GROWTH_REDDIT_BASE_URL=https://www.reddit.com
GROWTH_HN_BASE_URL=https://hn.algolia.com
GROWTH_LLM_MODEL=
GROWTH_LLM_SCORING_MODEL=
GROWTH_LLM_DRAFTING_MODEL=
GROWTH_LLM_BASE_URL=
GROWTH_LLM_API_KEY=
GROWTH_LLM_TIMEOUT_SECONDS=60
GROWTH_PRODUCT_NAME=
GROWTH_PRODUCT_URL=https://example.com
GROWTH_PRODUCT_DOMAIN=example.com
GROWTH_GLOBAL_DAILY_LIMIT=50
GROWTH_REDDIT_DAILY_LIMIT=5
GROWTH_SUBREDDIT_LINK_DAILY_LIMIT=2
GROWTH_FOLLOWUP_MAX_TOTAL=3
GROWTH_FOLLOWUP_MIN_INTERVAL_HOURS=24
GROWTH_WORKER_ID=growth-worker-1
GROWTH_WORKER_POLL_SECONDS=2
GROWTH_STALE_LOCK_SECONDS=600
```

- [ ] **Step 2: Write `server/docs/growth-runbook.md`**

Cover:
- Supabase project + database URL; run `python -m growth_core.migrate`.
- Seed: `python -m growth_core.scripts.seed --tenant-id ... --workspace-id ...`.
- Feishu app: permissions (`im:message`, `im:message:send_as_bot`), event subscription URL `/internal/v1/approvals/callback`, encrypt key/verification token, chat ID.
- n8n: every 30 minutes POST `/internal/v1/social/ingest` with `X-Service-Token`, tenant/workspace headers, and `Idempotency-Key: ingest-{{$now.toFormat('yyyyMMddHHmm')}}`.
- Worker: `python -m growth_social.worker`.
- API: `uvicorn growth_social.asgi:app --host 0.0.0.0 --port 8780`.
- Manual send: open Feishu card → copy draft → paste into platform → click “已发送”/POST sent. Never automate the platform.
- Troubleshooting: 401 token, 403 Feishu signature, `RATE_LIMITED`, `SUPPRESSED`, dead tasks, outbox dead letters.
- Acceptance checklist from spec §6.11 and DoD.

- [ ] **Step 3: Update README and tracking matrix**

`server/README.md` adds a short “Growth Agent” section pointing to the runbook and listing the two processes.

`GROWTH_AGENT_TRACKING.md` adds:
- Plan link: `docs/superpowers/plans/2026-11-15-growth-agent-phase0-module2.md`.
- Phase 0 / Module 2 status: `🔨` while implementing; after Task 24, mark completed rows `✅` and link the evidence commands.
- Add a “Phase 0/1 实现计划” row under the audit/traceability section.

- [ ] **Step 4: Verify docs references exist**

Run:

```bash
cd /Volumes/work/workspace/superAgent/ideas_pool
test -f docs/superpowers/plans/2026-11-15-growth-agent-phase0-module2.md
test -f server/docs/growth-runbook.md
test -f server/.env.growth.example
```

Expected: all commands exit 0.

- [ ] **Step 5: Commit**

```bash
git add server/.env.growth.example server/docs/growth-runbook.md server/README.md GROWTH_AGENT_TRACKING.md
git commit -m "docs: add growth agent runbook and tracking links"
```

---

## Task 24: Final verification and acceptance pass

**Files:**
- Modify: `GROWTH_AGENT_TRACKING.md`
- Test: all commands below

- [ ] **Step 1: Run the full existing + new unit suite**

```bash
cd /Volumes/work/workspace/superAgent/ideas_pool/server
python -m pytest -q
```

Expected: all existing Opportunity Scout tests pass plus all non-integration growth tests.

- [ ] **Step 2: Run Postgres integration tests**

```bash
cd /Volumes/work/workspace/superAgent/ideas_pool/server
GROWTH_TEST_DATABASE_URL=postgresql://... python -m pytest tests/growth/test_postgres_integration.py tests/growth/test_repository_postgres.py tests/growth/test_migrations.py tests/growth/test_seed.py -q
```

Expected: PASS (or skip if no database URL is provided; a release candidate requires PASS).

- [ ] **Step 3: Compile-check every package**

```bash
cd /Volumes/work/workspace/superAgent/ideas_pool/server
python -m compileall -q app opportunity_core growth_core growth_social
```

Expected: exit 0.

- [ ] **Step 4: Acceptance checklist**

Verify and record evidence:
- [ ] Ingest Reddit/HN mock → lead created once, dedupe works.
- [ ] High score → draft task; low score → dropped; watch → no draft.
- [ ] Draft has exactly one official link, UTM, disclosure; missing/extra link rejected.
- [ ] Feishu card contains title, score, draft, link, warning, approve/reject/edit/later.
- [ ] Approval is idempotent; rejection is recorded; revision creates a new version.
- [ ] Sent action records `sent_at`, `channel`, `draft_version`; duplicate send blocked.
- [ ] Global 50/day, Reddit 5/day, subreddit 2/day enforced at send time.
- [ ] Suppression blocks sending and follow-up.
- [ ] Follow-up max 1/day, max 3 total; stops on reply/negative feedback.
- [ ] No code path posts/comments/DMs on Reddit, HN, or any platform.
- [ ] Existing 43 backend tests + 22 frontend tests remain green; `npm run check` is unaffected.

- [ ] **Step 5: Update tracking matrix statuses and commit**

Mark Phase 0/1 rows `✅` only when the corresponding test evidence exists. Record the command outputs in the matrix or a linked file. Then:

```bash
git add GROWTH_AGENT_TRACKING.md
git commit -m "docs: mark phase 0 and module 2 complete"
```

---

## Spec Coverage Check

| Spec requirement | Task |
|---|---|
| Supabase Postgres single source of truth | 3, 4, 6 |
| Multi-tenant `tenant_id` / `workspace_id` + RLS | 4, 22 |
| `provider_configs`, `tenant_quotas`, `tenant_features`, `config_versions` | 3, 5, 6 |
| `pipeline_runs` queue + `SKIP LOCKED` + backoff + dead letter | 3, 6, 11, 22 |
| Outbox + idempotency | 3, 6, 11, 22 |
| Feishu notifier, signature, token verification | 9, 18 |
| Adapter registry + contracts | 10, 12, 13, 15 |
| Reddit + HN read-only ingestion, 30-minute cadence | 12, 13, 14, 23 |
| Dedupe by platform + post id | 14, 22 |
| Intent scoring rubric + penalties + thresholds | 5, 16 |
| Server computes score; model only supplies dimensions | 16 |
| Draft structure: empathy, value, soft mention, one link | 17 |
| Link policy: one link, deep link, UTM, disclosure, no shorteners | 17 |
| Subreddit rule check / manual-only handling | 17 |
| Feishu approval: approve/reject/edit/later, idempotent callback | 9, 18 |
| Manual send tracking, no auto-post | 19, 21 |
| Follow-up 1/day, max 3, stop on reply/negative feedback | 20 |
| Global 50/day, Reddit 5/day, subreddit 2/day | 5, 19 |
| Suppression list checked before send and follow-up | 19, 20 |
| Internal API `/internal/v1/*` + service token | 8, 18 |
| Admin endpoints for leads/messages/sent/revise | 8, 18, 19 |
| Tests: unit, integration, prompt regression, safety, e2e | 7–22 |
| Runbook + env example | 23 |

## Acceptance Criteria (Phase 0 + Module 2)

1. `python -m pytest -q` passes in `server/`, including all pre-existing tests.
2. With `GROWTH_TEST_DATABASE_URL` set, migrations, seed, queue/outbox concurrency, rate limits, and RLS tests pass.
3. The end-to-end test produces: 1 lead → 1 qualified score → 1 draft → 1 Feishu card → 1 approval → 1 sent record → 1 follow-up at +24h.
4. No reply can be created without exactly one official link, UTM, and disclosure.
5. No send is recorded when global/Reddit/subreddit limits or suppression rules are violated.
6. No follow-up is created after a reply, negative feedback, unsubscribe, moderator warning, or the third follow-up.
7. There is no code path that posts, comments, DMs, or logs into Reddit/HN; all sends are human-recorded.

## Self-Review Notes

- **Spec coverage:** Every Phase 0 and Module 2 requirement in spec §5, §6, and the relevant §11 extension points maps to a task above. Module 4, 1, and 3 are intentionally out of scope for this plan.
- **Type consistency:** `GrowthRepository` methods used by later tasks are all declared in Task 6. `RawPost`, `IntentScoreDraft`, `ReplyDraft`, `LinkPolicyResult`, `RateLimitCheck`, and `ApprovalResult` are defined before their consumers.
- **Review Focus mapping:** duplicate delivery → Tasks 6, 11, 14, 18, 22; unsafe LLM output → Task 17; send-time limits → Task 19; feedback after draft → Task 20; outbox crash/retry → Tasks 11, 22.
- **Deliberate decisions:** subreddits that disallow self-promotion links become `suppressed`, because every reply must contain one official link; the operator handles those manually outside the system. `mark_sent` records a human action and never calls a platform write API.
- **Deferred:** X adapter (M2.5), lifecycle/pSEO/repurpose modules, Admin UI pages (the plan exposes the API surface they will use), provider failover beyond config priority, and physical extraction of the analyzer into `opportunity_core`.

