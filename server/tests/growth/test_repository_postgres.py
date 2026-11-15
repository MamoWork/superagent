"""Integration tests for the Postgres Growth repository.

Each test creates fresh tenant/workspace UUIDs, so tests are isolated by
tenant and can be re-run against the same database without truncation.
``truncate_all_for_tests`` is available on the repository for callers that do
want a clean slate, but these tests deliberately do not use it: the focused
suite must be safely repeatable back-to-back.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timedelta, timezone

import asyncpg
import pytest

from growth_core.migrate import apply_migrations
from growth_core.repositories.postgres import PostgresGrowthRepository
from growth_core.schemas import (
    GrowthSource,
    NewOutboxMessage,
    NewOutreachMessage,
    NewOutreachVersion,
    NewSocialLead,
    NewTask,
    RateLimitCheck,
)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not os.getenv("GROWTH_TEST_DATABASE_URL"),
        reason="GROWTH_TEST_DATABASE_URL is not set",
    ),
]


@pytest.fixture
async def repo():
    url = os.environ["GROWTH_TEST_DATABASE_URL"]
    await apply_migrations(url)
    repository = await PostgresGrowthRepository.connect(url)
    try:
        yield repository
    finally:
        await repository.close()


def _utc(*args: int) -> datetime:
    return datetime(*args, tzinfo=timezone.utc)


async def _fresh_tenant(repo: PostgresGrowthRepository) -> tuple[uuid.UUID, uuid.UUID]:
    tenant_id, workspace_id = uuid.uuid4(), uuid.uuid4()
    await repo.ensure_tenant(tenant_id, workspace_id)
    return tenant_id, workspace_id


async def _clear_task6_tasks(repo: PostgresGrowthRepository) -> None:
    """Remove only this module's task rows so focused re-runs stay isolated.

    ``claim_task`` intentionally has no tenant argument (workers are global),
    so a queued task left behind by an earlier run could otherwise be picked
    up before the task under test. Every task in this module is tagged with a
    ``task6:`` pipeline prefix, making a narrow cleanup safe.
    """
    await repo._pool.execute(
        "delete from pipeline_runs where pipeline like 'task6:%'"
    )


async def test_enqueue_task_is_idempotent(repo):
    tenant_id, workspace_id = await _fresh_tenant(repo)
    await _clear_task6_tasks(repo)
    task = NewTask(
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        pipeline="task6:ingest",
        task_type="social.ingest",
        payload={},
        idempotency_key="ingest:1",
    )

    first = await repo.enqueue_task(task)
    second = await repo.enqueue_task(task)

    assert first == second
    assert (
        await repo._pool.fetchval(
            "select count(*) from pipeline_runs "
            "where tenant_id = $1 and idempotency_key = $2",
            tenant_id,
            "ingest:1",
        )
        == 1
    )


async def test_claim_task_returns_one_and_marks_running(repo):
    tenant_id, workspace_id = await _fresh_tenant(repo)
    await _clear_task6_tasks(repo)
    run_after = _utc(2020, 1, 1)
    now = run_after + timedelta(minutes=1)
    task_id = await repo.enqueue_task(
        NewTask(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            pipeline="task6:claim-one",
            task_type="social.ingest",
            idempotency_key="claim:one",
            priority=-1000,
            run_after=run_after,
        )
    )

    claimed = await repo.claim_task("worker-1", now=now)

    assert claimed is not None
    assert claimed.id == task_id
    assert claimed.status == "running"
    assert claimed.locked_by == "worker-1"
    assert claimed.locked_at is not None
    assert claimed.attempts == 0

    # A second worker cannot claim the same row.
    second = await repo.claim_task("worker-2", now=now)
    assert second is None or second.id != task_id

    await repo.complete_task(task_id)


async def test_fail_task_backs_off_then_dead_letters(repo):
    tenant_id, workspace_id = await _fresh_tenant(repo)
    await _clear_task6_tasks(repo)
    t0 = _utc(2018, 1, 1)
    task_id = await repo.enqueue_task(
        NewTask(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            pipeline="task6:fail",
            task_type="social.ingest",
            idempotency_key="fail:backoff",
            priority=-1000,
            run_after=t0,
            max_attempts=2,
        )
    )

    claimed = await repo.claim_task("worker", now=t0)
    assert claimed is not None and claimed.id == task_id

    await repo.fail_task(task_id, "boom", now=t0)
    row = await repo._pool.fetchrow(
        "select status, attempts, run_after from pipeline_runs where id = $1",
        task_id,
    )
    assert row["status"] == "queued"
    assert row["attempts"] == 1
    # attempts was 0 when failing, so the delay is 60 * 2**0 seconds.
    assert row["run_after"] == t0 + timedelta(seconds=60)

    # Not eligible before the backoff expires.
    assert await repo.claim_task("worker", now=t0 + timedelta(seconds=59)) is None

    claimed = await repo.claim_task("worker", now=t0 + timedelta(seconds=60))
    assert claimed is not None and claimed.id == task_id

    await repo.fail_task(task_id, "boom again", now=t0 + timedelta(seconds=60))
    row = await repo._pool.fetchrow(
        "select status, attempts from pipeline_runs where id = $1", task_id
    )
    assert row["status"] == "dead"
    assert row["attempts"] == 2

    assert await repo.claim_task("worker", now=t0 + timedelta(days=1)) is None


async def test_outbox_idempotent_and_retry(repo):
    tenant_id, workspace_id = await _fresh_tenant(repo)
    t0 = _utc(2019, 1, 1)
    message = NewOutboxMessage(
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        topic="feishu.card",
        payload={"approval_id": "a:1"},
        idempotency_key="feishu:a:1",
        next_attempt_at=t0,
    )

    first = await repo.enqueue_outbox(message)
    second = await repo.enqueue_outbox(message)
    assert first == second

    claimed = await repo.claim_outbox(limit=50, now=t0)
    ours = [item for item in claimed if item.id == first]
    assert len(ours) == 1
    assert ours[0].status == "sending"

    now = t0
    for attempt in range(1, 5):
        await repo.mark_outbox_failed(first, f"error-{attempt}", now=now)
        row = await repo._pool.fetchrow(
            "select status, attempts, next_attempt_at from outbox_messages "
            "where id = $1",
            first,
        )
        assert row["attempts"] == attempt
        assert row["status"] == "failed"
        # attempts before this failure was attempt - 1.
        assert row["next_attempt_at"] == now + timedelta(
            seconds=60 * 2 ** (attempt - 1)
        )

        now = row["next_attempt_at"]
        claimed = await repo.claim_outbox(limit=50, now=now)
        assert any(item.id == first for item in claimed)

    await repo.mark_outbox_failed(first, "final error", now=now)
    row = await repo._pool.fetchrow(
        "select status, attempts from outbox_messages where id = $1", first
    )
    assert row["status"] == "dead"
    assert row["attempts"] == 5

    later = await repo.claim_outbox(limit=50, now=now + timedelta(days=365))
    assert all(item.id != first for item in later)


async def test_consume_rate_limits_is_atomic(repo):
    tenant_id, _ = await _fresh_tenant(repo)
    now = _utc(2020, 6, 1, 12, 0)
    check = RateLimitCheck(
        scope="global", scope_key="*", max_count=2, window_seconds=86400
    )

    allowed = await repo.consume_rate_limits(tenant_id, [check, check], now=now)
    assert allowed.allowed is True

    denied = await repo.consume_rate_limits(tenant_id, [check, check], now=now)
    assert denied.allowed is False
    assert denied.exceeded_scope == "global"
    assert denied.exceeded_scope_key == "*"
    assert denied.retry_after_seconds > 0

    window_start = now - timedelta(
        seconds=int(now.timestamp()) % check.window_seconds
    )
    assert (
        await repo._pool.fetchval(
            "select count from rate_limit_counters "
            "where tenant_id = $1 and channel = $2 and scope = $3 "
            "and scope_key = $4 and window_start = $5",
            tenant_id,
            check.channel,
            "global",
            "*",
            window_start,
        )
        == 2
    )


async def test_upsert_lead_deduplicates(repo):
    tenant_id, workspace_id = await _fresh_tenant(repo)
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

    first, created = await repo.upsert_lead(lead)
    second, created_again = await repo.upsert_lead(
        lead.model_copy(update={"title": "Changed title"})
    )

    assert created is True
    assert created_again is False
    assert second.id == first.id
    assert second.title == "Original title"
    assert second.status == "discovered"

    fetched = await repo.get_lead(tenant_id, first.id)
    assert fetched is not None and fetched.id == first.id


async def test_consume_rate_limits_rolls_back_all_checks(repo):
    tenant_id, _ = await _fresh_tenant(repo)
    now = _utc(2020, 7, 1, 12, 0)
    first_check = RateLimitCheck(
        scope="global", scope_key="*", max_count=5, window_seconds=86400
    )
    second_check = RateLimitCheck(
        scope="platform", scope_key="reddit", max_count=1, window_seconds=86400
    )

    # Exhaust the second check.
    assert (
        await repo.consume_rate_limits(tenant_id, [second_check], now=now)
    ).allowed is True

    decision = await repo.consume_rate_limits(
        tenant_id, [first_check, second_check], now=now
    )
    assert decision.allowed is False
    assert decision.exceeded_scope == "platform"
    assert decision.exceeded_scope_key == "reddit"

    window_start = now - timedelta(
        seconds=int(now.timestamp()) % first_check.window_seconds
    )
    first_count = await repo._pool.fetchval(
        "select count from rate_limit_counters "
        "where tenant_id = $1 and channel = $2 and scope = $3 "
        "and scope_key = $4 and window_start = $5",
        tenant_id,
        first_check.channel,
        "global",
        "*",
        window_start,
    )
    # The first check had room but its increment was rolled back.
    assert first_count is None

    second_count = await repo._pool.fetchval(
        "select count from rate_limit_counters "
        "where tenant_id = $1 and channel = $2 and scope = $3 "
        "and scope_key = $4 and window_start = $5",
        tenant_id,
        second_check.channel,
        "platform",
        "reddit",
        window_start,
    )
    assert second_count == 1


async def test_rollback_config_version_restores_snapshot(repo):
    tenant_id, _ = await _fresh_tenant(repo)
    prompt_id = uuid.uuid4()
    await repo._pool.execute(
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
    version_id = await repo._pool.fetchval(
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

    assert await repo.rollback_config_version(tenant_id, version_id, "operator")

    row = await repo._pool.fetchrow(
        "select * from prompt_templates where id = $1", prompt_id
    )
    assert row["template"] == "old system"
    assert row["user_template"] == "old user"
    assert row["version"] == 1

    versions = await repo._pool.fetch(
        """
        select version, diff, snapshot, changed_by from config_versions
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

    bad_version_id = await repo._pool.fetchval(
        """
        insert into config_versions
            (tenant_id, table_name, record_id, version, diff, snapshot,
             changed_by)
        values ($1, 'rate_limit_rules', $2, 1, '{}'::jsonb, '{}'::jsonb, 'x')
        returning id
        """,
        tenant_id,
        uuid.uuid4(),
    )
    with pytest.raises(ValueError):
        await repo.rollback_config_version(tenant_id, bad_version_id, "operator")

    assert not await repo.rollback_config_version(
        tenant_id, uuid.uuid4(), "operator"
    )


async def test_claim_task_honors_now(repo):
    tenant_id, workspace_id = await _fresh_tenant(repo)
    await _clear_task6_tasks(repo)
    run_after = _utc(2021, 1, 1)
    task_id = await repo.enqueue_task(
        NewTask(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            pipeline="task6:honors",
            task_type="social.ingest",
            idempotency_key="claim:honors-now",
            priority=-1000,
            run_after=run_after,
        )
    )

    early = await repo.claim_task(
        "worker", now=run_after - timedelta(seconds=1)
    )
    assert early is None or early.id != task_id

    claimed = await repo.claim_task("worker", now=run_after)
    assert claimed is not None
    assert claimed.id == task_id

    await repo.complete_task(task_id)


async def test_update_message_status_is_compare_and_set(repo):
    tenant_id, workspace_id = await _fresh_tenant(repo)
    message = await repo.create_message(
        NewOutreachMessage(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            channel="social",
            status="draft_ready",
            dedupe_key="message:cas",
            metadata={"a": 1},
        )
    )

    wrong = await repo.update_message_status(
        tenant_id,
        message.id,
        expected_status="approved",
        status="sent",
        metadata_patch={"b": 2},
    )
    assert wrong is False

    unchanged = await repo.get_message(tenant_id, message.id)
    assert unchanged is not None
    assert unchanged.status == "draft_ready"
    assert unchanged.metadata == {"a": 1}
    assert unchanged.version == 1

    sent_at = _utc(2022, 1, 1)
    right = await repo.update_message_status(
        tenant_id,
        message.id,
        expected_status="draft_ready",
        status="approved",
        sent_at=sent_at,
        provider="reddit",
        provider_message_id="provider-1",
        metadata_patch={"b": 2},
    )
    assert right is True

    updated = await repo.get_message(tenant_id, message.id)
    assert updated is not None
    assert updated.status == "approved"
    assert updated.metadata == {"a": 1, "b": 2}
    assert updated.sent_at == sent_at
    assert updated.provider == "reddit"
    assert updated.provider_message_id == "provider-1"
    assert updated.version == 2

    # The expected-status guard still applies after the transition.
    assert (
        await repo.update_message_status(
            tenant_id,
            message.id,
            expected_status="draft_ready",
            status="sent",
        )
        is False
    )


async def test_stale_terminal_writes_are_fenced_and_reclaim_counts_attempts(repo):
    tenant_id, workspace_id = await _fresh_tenant(repo)
    await _clear_task6_tasks(repo)
    t0 = _utc(2018, 2, 1)
    task_id = await repo.enqueue_task(
        NewTask(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            pipeline="task6:stale",
            task_type="social.ingest",
            idempotency_key="stale:1",
            priority=-1000,
            run_after=t0,
            max_attempts=5,
        )
    )

    first_claim = await repo.claim_task("worker-a", now=t0)
    assert first_claim is not None and first_claim.id == task_id

    reclaimed = await repo.reclaim_stale_tasks(0, now=t0 + timedelta(seconds=1))
    assert reclaimed >= 1
    row = await repo._pool.fetchrow(
        "select status, attempts, locked_by from pipeline_runs where id = $1",
        task_id,
    )
    assert row["status"] == "queued"
    assert row["attempts"] == 1
    assert row["locked_by"] is None

    # The original worker must not complete a row it no longer owns.
    await repo.complete_task(task_id, "worker-a")
    row = await repo._pool.fetchrow(
        "select status, attempts from pipeline_runs where id = $1", task_id
    )
    assert row["status"] == "queued"
    assert row["attempts"] == 1

    second_claim = await repo.claim_task(
        "worker-b", now=t0 + timedelta(seconds=2)
    )
    assert second_claim is not None and second_claim.id == task_id
    assert second_claim.locked_by == "worker-b"
    assert second_claim.attempts == 1

    # A stale fail from the old worker must not touch the new owner's row.
    await repo.fail_task(
        task_id,
        "stale worker",
        now=t0 + timedelta(seconds=3),
        worker_id="worker-a",
    )
    row = await repo._pool.fetchrow(
        "select status, attempts, locked_by from pipeline_runs where id = $1",
        task_id,
    )
    assert row["status"] == "running"
    assert row["attempts"] == 1
    assert row["locked_by"] == "worker-b"

    # The current owner can still fail it.
    await repo.fail_task(
        task_id,
        "real failure",
        now=t0 + timedelta(seconds=3),
        worker_id="worker-b",
    )
    row = await repo._pool.fetchrow(
        "select status, attempts from pipeline_runs where id = $1", task_id
    )
    assert row["status"] == "queued"
    assert row["attempts"] == 2


async def test_outbox_terminal_writes_are_fenced(repo):
    tenant_id, workspace_id = await _fresh_tenant(repo)
    t0 = _utc(2019, 2, 1)
    outbox_id = await repo.enqueue_outbox(
        NewOutboxMessage(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            topic="feishu.card",
            payload={},
            idempotency_key="outbox:fence",
            next_attempt_at=t0,
        )
    )

    # pending -> sent is a no-op.
    await repo.mark_outbox_sent(outbox_id)
    row = await repo._pool.fetchrow(
        "select status, attempts from outbox_messages where id = $1", outbox_id
    )
    assert row["status"] == "pending"
    assert row["attempts"] == 0

    claimed = await repo.claim_outbox(limit=50, now=t0)
    assert any(item.id == outbox_id for item in claimed)

    # sending -> sent is the valid transition.
    await repo.mark_outbox_sent(outbox_id)
    row = await repo._pool.fetchrow(
        "select status, attempts from outbox_messages where id = $1", outbox_id
    )
    assert row["status"] == "sent"

    # sent -> failed is a no-op and must not make the row re-claimable.
    await repo.mark_outbox_failed(
        outbox_id, "late failure", now=t0 + timedelta(seconds=1)
    )
    row = await repo._pool.fetchrow(
        "select status, attempts from outbox_messages where id = $1", outbox_id
    )
    assert row["status"] == "sent"
    assert row["attempts"] == 0


async def test_rate_limit_zero_max_count_blocks_without_incrementing(repo):
    tenant_id, _ = await _fresh_tenant(repo)
    now = _utc(2020, 8, 1, 12, 0)
    room = RateLimitCheck(
        scope="global", scope_key="*", max_count=5, window_seconds=86400
    )
    blocked = RateLimitCheck(
        scope="platform", scope_key="reddit", max_count=0, window_seconds=86400
    )

    decision = await repo.consume_rate_limits(
        tenant_id, [room, blocked], now=now
    )

    assert decision.allowed is False
    assert decision.exceeded_scope == "platform"
    assert decision.exceeded_scope_key == "reddit"
    assert decision.retry_after_seconds > 0
    assert (
        await repo._pool.fetchval(
            "select count(*) from rate_limit_counters where tenant_id = $1",
            tenant_id,
        )
        == 0
    )


async def test_naive_model_datetimes_are_stored_as_utc():
    url = os.environ["GROWTH_TEST_DATABASE_URL"]
    await apply_migrations(url)
    # Use a non-UTC session as an extra guard: asyncpg encodes a naive
    # datetime using the process-local zone, so without normalization the
    # stored instant would differ from the intended UTC value.
    pool = await asyncpg.create_pool(
        url, server_settings={"timezone": "America/New_York"}
    )
    repo = PostgresGrowthRepository(pool)
    try:
        tenant_id, workspace_id = uuid.uuid4(), uuid.uuid4()
        await repo.ensure_tenant(tenant_id, workspace_id)
        await _clear_task6_tasks(repo)
        naive = datetime(2017, 1, 1, 12, 0)
        expected = naive.replace(tzinfo=timezone.utc)

        task_id = await repo.enqueue_task(
            NewTask(
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                pipeline="task6:naive-tz",
                task_type="social.ingest",
                idempotency_key="naive:run-after",
                run_after=naive,
            )
        )
        assert (
            await repo._pool.fetchval(
                "select run_after from pipeline_runs where id = $1", task_id
            )
            == expected
        )

        outbox_id = await repo.enqueue_outbox(
            NewOutboxMessage(
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                topic="feishu.card",
                payload={},
                idempotency_key="naive:outbox",
                next_attempt_at=naive,
            )
        )
        assert (
            await repo._pool.fetchval(
                "select next_attempt_at from outbox_messages where id = $1",
                outbox_id,
            )
            == expected
        )

        source = GrowthSource(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            source_type="reddit",
            platform="reddit",
            dedupe_key="naive:source",
            last_run_at=naive,
        )
        await repo.add_source(source)
        assert (
            await repo._pool.fetchval(
                "select last_run_at from growth_sources where id = $1",
                source.id,
            )
            == expected
        )

        lead, _ = await repo.upsert_lead(
            NewSocialLead(
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                platform="reddit",
                platform_post_id="naive-post",
                source_url="https://example.com/naive",
                dedupe_key="naive:lead",
                published_at=naive,
            )
        )
        assert (
            await repo._pool.fetchval(
                "select published_at from social_leads where id = $1", lead.id
            )
            == expected
        )

        message = await repo.create_message(
            NewOutreachMessage(
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                channel="social",
                status="draft_ready",
                dedupe_key="naive:message",
                scheduled_at=naive,
            )
        )
        assert (
            await repo._pool.fetchval(
                "select scheduled_at from outreach_messages where id = $1",
                message.id,
            )
            == expected
        )

        version = await repo.create_version(
            NewOutreachVersion(
                tenant_id=tenant_id,
                message_id=message.id,
                version=1,
                body_text="body",
            )
        )
        await repo.mark_version_approved(
            tenant_id, version.id, "operator", naive
        )
        assert (
            await repo._pool.fetchval(
                "select approved_at from outreach_versions where id = $1",
                version.id,
            )
            == expected
        )
    finally:
        await repo.close()
