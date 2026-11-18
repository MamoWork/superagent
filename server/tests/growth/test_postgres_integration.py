"""Postgres integration tests for queue, outbox, rate limits, and RLS.

These tests require a live Postgres database and are skipped unless
``GROWTH_TEST_DATABASE_URL`` is set. The ``pg_repo`` fixture applies the
migrations, truncates every Growth table, and yields a connected repository,
so each test starts from a clean database and the global worker queue
(``claim_task`` has no tenant argument) contains only the test's own rows.
"""

from __future__ import annotations

import asyncio
import json
import os
import uuid
from datetime import datetime, timedelta, timezone

import asyncpg
import pytest

from growth_core.repositories.postgres import PostgresGrowthRepository
from growth_core.schemas import (
    NewOutboxMessage,
    NewSocialLead,
    NewTask,
    RateLimitCheck,
)
from growth_social.services.feedback import record_feedback

pytestmark = pytest.mark.integration

_RLS_ROLE = "growth_test_app"


def _utc(*args: int) -> datetime:
    return datetime(*args, tzinfo=timezone.utc)


async def _ensure_tenant(
    repo: PostgresGrowthRepository,
) -> tuple[uuid.UUID, uuid.UUID]:
    tenant_id, workspace_id = uuid.uuid4(), uuid.uuid4()
    await repo.ensure_tenant(tenant_id, workspace_id)
    return tenant_id, workspace_id


async def _connect_second_repository() -> PostgresGrowthRepository:
    """Open a second pool so two workers use independent connections."""
    return await PostgresGrowthRepository.connect(
        os.environ["GROWTH_TEST_DATABASE_URL"]
    )


async def _ensure_rls_role(repo: PostgresGrowthRepository) -> None:
    """Create and grant the non-owner role used by the RLS test.

    The role is created with autocommit on purpose: role creation is durable.
    Grants are repeated on every run, which is harmless and keeps the test
    self-healing if the database was reset.
    """
    async with repo._pool.acquire() as conn:
        try:
            await conn.execute(f"create role {_RLS_ROLE} nologin")
        except asyncpg.exceptions.DuplicateObjectError:
            pass
        await conn.execute(f"grant usage on schema public to {_RLS_ROLE}")
        # The tenant_isolation policy calls auth.jwt().
        await conn.execute(f"grant usage on schema auth to {_RLS_ROLE}")
        await conn.execute(f"grant select on social_leads to {_RLS_ROLE}")


@pytest.mark.skipif(
    not os.getenv("GROWTH_TEST_DATABASE_URL"), reason="no test DB"
)
async def test_two_workers_claim_distinct_tasks(pg_repo, now):
    tenant_id, workspace_id = await _ensure_tenant(pg_repo)
    t0 = _utc(2018, 1, 1)
    task_ids = set()
    for index in (1, 2):
        task_ids.add(
            await pg_repo.enqueue_task(
                NewTask(
                    tenant_id=tenant_id,
                    workspace_id=workspace_id,
                    pipeline="task22:two-workers",
                    task_type="social.ingest",
                    idempotency_key=f"two-workers:{index}",
                    run_after=t0,
                )
            )
        )

    second = await _connect_second_repository()
    try:
        barrier = asyncio.Barrier(2)

        async def worker(
            repo: PostgresGrowthRepository, worker_id: str
        ):
            await barrier.wait()
            return worker_id, await repo.claim_task(worker_id, now=t0)

        results = await asyncio.gather(
            worker(pg_repo, "worker-a"),
            worker(second, "worker-b"),
        )
    finally:
        await second.close()

    claimed = [task for _, task in results]
    assert all(task is not None for task in claimed)
    claimed_ids = {task.id for task in claimed}
    assert len(claimed_ids) == 2
    assert claimed_ids == task_ids
    assert all(task.status == "running" for task in claimed)
    assert {(worker_id, task.locked_by) for worker_id, task in results} == {
        ("worker-a", "worker-a"),
        ("worker-b", "worker-b"),
    }


@pytest.mark.skipif(
    not os.getenv("GROWTH_TEST_DATABASE_URL"), reason="no test DB"
)
async def test_rate_limit_is_atomic_under_concurrency(pg_repo, now):
    tenant_id, _ = await _ensure_tenant(pg_repo)
    t0 = _utc(2020, 6, 1, 12, 0)
    check = RateLimitCheck(
        scope="global", scope_key="*", max_count=1, window_seconds=86400
    )

    second = await _connect_second_repository()
    try:
        barrier = asyncio.Barrier(2)

        async def consume(repo: PostgresGrowthRepository):
            await barrier.wait()
            return await repo.consume_rate_limits(tenant_id, [check], now=t0)

        decisions = await asyncio.gather(
            consume(pg_repo),
            consume(second),
        )
    finally:
        await second.close()

    assert sum(1 for decision in decisions if decision.allowed) == 1
    denied = [decision for decision in decisions if not decision.allowed]
    assert len(denied) == 1
    assert denied[0].exceeded_scope == "global"
    assert denied[0].exceeded_scope_key == "*"

    window_start = t0 - timedelta(
        seconds=int(t0.timestamp()) % check.window_seconds
    )
    count = await pg_repo._pool.fetchval(
        """
        select count from rate_limit_counters
        where tenant_id = $1 and channel = $2 and scope = $3
          and scope_key = $4 and window_start = $5
        """,
        tenant_id,
        check.channel,
        "global",
        "*",
        window_start,
    )
    assert count == 1


@pytest.mark.skipif(
    not os.getenv("GROWTH_TEST_DATABASE_URL"), reason="no test DB"
)
async def test_rls_hides_other_tenant(pg_repo):
    tenant_a, workspace_a = await _ensure_tenant(pg_repo)
    tenant_b, workspace_b = await _ensure_tenant(pg_repo)
    for tenant_id, workspace_id, suffix in (
        (tenant_a, workspace_a, "a"),
        (tenant_b, workspace_b, "b"),
    ):
        created, _ = await pg_repo.upsert_lead(
            NewSocialLead(
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                platform="reddit",
                platform_post_id=f"rls-post-{suffix}",
                source_url=f"https://example.com/rls-{suffix}",
                dedupe_key=f"rls-lead-{suffix}",
            )
        )
        assert created.tenant_id == tenant_id

    await _ensure_rls_role(pg_repo)

    async with pg_repo._pool.acquire() as conn:
        async with conn.transaction():
            # SET LOCAL ROLE is transaction scoped, reset explicitly anyway.
            await conn.execute(f"set local role {_RLS_ROLE}")

            async def visible_tenants(tenant_id: uuid.UUID) -> list[str]:
                await conn.execute(
                    "select set_config('request.jwt.claims', $1, true)",
                    json.dumps({"tenant_id": str(tenant_id)}),
                )
                return await conn.fetchval("select count(*) from social_leads")

            assert await visible_tenants(tenant_a) == 1
            visible_a = await conn.fetchval(
                "select tenant_id::text from social_leads"
            )
            assert visible_a == str(tenant_a)

            assert await visible_tenants(tenant_b) == 1
            visible_b = await conn.fetchval(
                "select tenant_id::text from social_leads"
            )
            assert visible_b == str(tenant_b)

            assert await visible_tenants(uuid.uuid4()) == 0

            await conn.execute("reset role")

    # Superuser access is unrestricted again after the transaction.
    assert await pg_repo._pool.fetchval("select count(*) from social_leads") == 2


@pytest.mark.skipif(
    not os.getenv("GROWTH_TEST_DATABASE_URL"), reason="no test DB"
)
async def test_fail_task_backoff_and_dead_letter(pg_repo, now):
    tenant_id, workspace_id = await _ensure_tenant(pg_repo)
    t0 = _utc(2018, 2, 1)
    task_id = await pg_repo.enqueue_task(
        NewTask(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            pipeline="task22:fail",
            task_type="social.ingest",
            idempotency_key="fail:backoff",
            run_after=t0,
            max_attempts=2,
        )
    )

    claimed = await pg_repo.claim_task("worker", now=t0)
    assert claimed is not None and claimed.id == task_id

    await pg_repo.fail_task(task_id, "boom", now=t0)
    row = await pg_repo._pool.fetchrow(
        "select status, attempts, run_after from pipeline_runs where id = $1",
        task_id,
    )
    assert row["status"] == "queued"
    assert row["attempts"] == 1
    # attempts was 0 when this failure was recorded: 60 * 2**0 seconds.
    assert row["run_after"] == t0 + timedelta(seconds=60)

    assert (
        await pg_repo.claim_task("worker", now=t0 + timedelta(seconds=59))
        is None
    )
    reclaimed = await pg_repo.claim_task(
        "worker", now=t0 + timedelta(seconds=60)
    )
    assert reclaimed is not None and reclaimed.id == task_id

    await pg_repo.fail_task(
        task_id, "boom again", now=t0 + timedelta(seconds=60)
    )
    row = await pg_repo._pool.fetchrow(
        "select status, attempts, last_error from pipeline_runs where id = $1",
        task_id,
    )
    assert row["status"] == "dead"
    assert row["attempts"] == 2
    assert row["last_error"] == "boom again"
    assert (
        await pg_repo.claim_task("worker", now=t0 + timedelta(days=1)) is None
    )


@pytest.mark.skipif(
    not os.getenv("GROWTH_TEST_DATABASE_URL"), reason="no test DB"
)
async def test_outbox_retry_marks_sent(pg_repo, now):
    tenant_id, workspace_id = await _ensure_tenant(pg_repo)
    t0 = _utc(2019, 1, 1)
    outbox_id = await pg_repo.enqueue_outbox(
        NewOutboxMessage(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            topic="feishu.card",
            payload={"approval_id": "a:1"},
            idempotency_key="task22:outbox:1",
            next_attempt_at=t0,
        )
    )

    claimed = await pg_repo.claim_outbox(limit=50, now=t0)
    assert [message.id for message in claimed] == [outbox_id]
    assert claimed[0].status == "sending"

    await pg_repo.mark_outbox_failed(outbox_id, "transient", now=t0)
    row = await pg_repo._pool.fetchrow(
        "select status, attempts, next_attempt_at, last_error "
        "from outbox_messages where id = $1",
        outbox_id,
    )
    assert row["status"] == "failed"
    assert row["attempts"] == 1
    assert row["next_attempt_at"] == t0 + timedelta(seconds=60)
    assert row["last_error"] == "transient"

    assert await pg_repo.claim_outbox(limit=50, now=t0 + timedelta(seconds=59)) == []

    retried = await pg_repo.claim_outbox(
        limit=50, now=t0 + timedelta(seconds=60)
    )
    assert [message.id for message in retried] == [outbox_id]
    await pg_repo.mark_outbox_sent(outbox_id)

    row = await pg_repo._pool.fetchrow(
        "select status, attempts, last_error from outbox_messages where id = $1",
        outbox_id,
    )
    assert row["status"] == "sent"
    assert row["attempts"] == 1
    assert row["last_error"] is None
    assert (
        await pg_repo.claim_outbox(limit=50, now=t0 + timedelta(days=1)) == []
    )


@pytest.mark.skipif(
    not os.getenv("GROWTH_TEST_DATABASE_URL"), reason="no test DB"
)
async def test_upsert_lead_dedupes(pg_repo, now):
    tenant_id, workspace_id = await _ensure_tenant(pg_repo)
    lead = NewSocialLead(
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        platform="reddit",
        platform_post_id="post-1",
        title="Original title",
        body="Original body",
        source_url="https://example.com/post-1",
        dedupe_key="lead:dedupe",
    )

    first, created = await pg_repo.upsert_lead(lead)
    second, created_again = await pg_repo.upsert_lead(
        lead.model_copy(update={"title": "Changed title"})
    )

    assert created is True
    assert created_again is False
    assert second.id == first.id
    assert second.title == "Original title"
    assert second.status == "discovered"
    assert (
        await pg_repo._pool.fetchval("select count(*) from social_leads")
        == 1
    )


@pytest.mark.skipif(
    not os.getenv("GROWTH_TEST_DATABASE_URL"), reason="no test DB"
)
async def test_claim_task_skip_locked_with_two_connections(pg_repo, now):
    tenant_id, workspace_id = await _ensure_tenant(pg_repo)
    t0 = _utc(2018, 3, 1)
    task_id = await pg_repo.enqueue_task(
        NewTask(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            pipeline="task22:skip-locked",
            task_type="social.ingest",
            idempotency_key="skip-locked:1",
            run_after=t0,
        )
    )

    second = await _connect_second_repository()
    try:
        barrier = asyncio.Barrier(2)

        async def worker(repo: PostgresGrowthRepository, worker_id: str):
            await barrier.wait()
            return worker_id, await repo.claim_task(worker_id, now=t0)

        results = await asyncio.gather(
            worker(pg_repo, "worker-a"),
            worker(second, "worker-b"),
        )
    finally:
        await second.close()

    winners = [(worker_id, task) for worker_id, task in results if task]
    losers = [(worker_id, task) for worker_id, task in results if task is None]
    assert len(winners) == 1
    assert len(losers) == 1
    winner_id, winner_task = winners[0]
    assert winner_task.id == task_id
    assert winner_task.status == "running"
    assert winner_task.locked_by == winner_id

    row = await pg_repo._pool.fetchrow(
        "select status, locked_by from pipeline_runs where id = $1", task_id
    )
    assert row["status"] == "running"
    assert row["locked_by"] == winner_id
    # Nothing else is claimable.
    assert await pg_repo.claim_task("worker-c", now=t0) is None


@pytest.mark.skipif(
    not os.getenv("GROWTH_TEST_DATABASE_URL"), reason="no test DB"
)
async def test_config_rollback_restores_snapshot(pg_repo, now):
    tenant_id, _ = await _ensure_tenant(pg_repo)
    prompt_id = uuid.uuid4()
    await pg_repo._pool.execute(
        """
        insert into prompt_templates
            (id, tenant_id, key, module, version, template, user_template,
             output_schema, model_hint, enabled)
        values ($1, $2, 'rollback_key', 'social', 2, 'new system', 'new user',
                '{"type": "object"}'::jsonb, null, true)
        """,
        prompt_id,
        tenant_id,
    )
    snapshot = {
        "id": str(prompt_id),
        "tenant_id": str(tenant_id),
        "key": "rollback_key",
        "module": "social",
        "version": 1,
        "template": "old system",
        "user_template": "old user",
        "output_schema": {"type": "object"},
        "model_hint": None,
        "enabled": True,
    }
    version_id = await pg_repo._pool.fetchval(
        """
        insert into config_versions
            (tenant_id, table_name, record_id, version, diff, snapshot,
             changed_by)
        values ($1, 'prompt_templates', $2, 1, '{}'::jsonb, $3::jsonb, 'tester')
        returning id
        """,
        tenant_id,
        prompt_id,
        json.dumps(snapshot),
    )

    assert await pg_repo.rollback_config_version(
        tenant_id, version_id, "operator"
    )

    row = await pg_repo._pool.fetchrow(
        "select * from prompt_templates where id = $1", prompt_id
    )
    assert row["template"] == "old system"
    assert row["user_template"] == "old user"
    assert row["version"] == 1

    versions = await pg_repo._pool.fetch(
        """
        select version, diff, snapshot, changed_by
        from config_versions
        where tenant_id = $1 and table_name = 'prompt_templates'
          and record_id = $2
        order by version
        """,
        tenant_id,
        prompt_id,
    )
    assert [item["version"] for item in versions] == [1, 2]
    rollback_row = versions[-1]
    assert json.loads(rollback_row["diff"]) == {
        "rolled_back_from": str(version_id),
        "restored": True,
    }
    assert rollback_row["changed_by"] == "operator"
    assert json.loads(rollback_row["snapshot"])["template"] == "old system"


@pytest.mark.skipif(
    not os.getenv("GROWTH_TEST_DATABASE_URL"), reason="no test DB"
)
async def test_feedback_postgres_all_kinds_suppression_and_audit(pg_repo):
    tenant_id, workspace_id = await _ensure_tenant(pg_repo)
    cases = (
        ("replied", "replied", None),
        ("negative", "suppressed", "negative_reply"),
        ("unsubscribe", "suppressed", "unsubscribe"),
        ("moderator_warning", "suppressed", "moderator_warning"),
    )

    for kind, expected_status, expected_reason in cases:
        author = f"author-{kind}"
        lead, created = await pg_repo.upsert_lead(
            NewSocialLead(
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                platform="reddit",
                platform_post_id=f"feedback-{kind}",
                title="How do you keep onboarding emails personal?",
                body="Our welcome sequence feels generic.",
                author_public=author,
                source_url=f"https://reddit.example/r/SaaS/post/{kind}",
                dedupe_key=f"feedback-lead-{kind}",
            )
        )
        assert created is True

        result = await record_feedback(
            pg_repo,
            tenant_id=tenant_id,
            lead_id=lead.id,
            kind=kind,
            evidence=f"{kind} evidence",
            source="webhook",
        )

        assert result.status == expected_status
        assert result.suppressed is (expected_status == "suppressed")
        stored = await pg_repo.get_lead(tenant_id, lead.id)
        assert stored is not None
        assert stored.status == expected_status

        reason = await pg_repo._pool.fetchval(
            """
            select reason from suppression_list
            where tenant_id = $1 and kind = 'platform_user' and value = $2
            """,
            tenant_id,
            f"reddit:{author}",
        )
        assert reason == expected_reason

        audit = await pg_repo._pool.fetchrow(
            """
            select actor_type, actor_id,
                   after->>'kind' as kind,
                   after->>'status' as status,
                   after->>'suppressed' as suppressed
            from audit_log
            where tenant_id = $1 and action = 'social.feedback'
              and entity_id = $2
            """,
            tenant_id,
            lead.id,
        )
        assert audit is not None
        assert audit["actor_type"] == "integration"
        assert audit["actor_id"] == "webhook"
        assert audit["kind"] == kind
        assert audit["status"] == expected_status
        assert audit["suppressed"] == (
            "true" if expected_status == "suppressed" else "false"
        )
