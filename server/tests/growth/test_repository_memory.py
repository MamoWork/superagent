"""Unit tests for :class:`FakeGrowthRepository`.

These tests are DB-free and mirror the fencing/compare-and-set semantics of
the Postgres repository so later tasks can rely on the fake.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from growth_core.repositories.base import GrowthRepository
from growth_core.schemas import (
    NewApprovalRequest,
    NewOutboxMessage,
    NewOutreachMessage,
    NewSocialLead,
    NewTask,
    RateLimitCheck,
)
from tests.growth.fakes import FakeGrowthRepository


def _task(
    tenant_id,
    workspace_id,
    key: str,
    *,
    run_after: datetime | None = None,
    priority: int = 100,
    max_attempts: int = 5,
) -> NewTask:
    return NewTask(
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        pipeline="social",
        task_type="social.ingest",
        payload={},
        idempotency_key=key,
        priority=priority,
        run_after=run_after,
        max_attempts=max_attempts,
    )


def test_fake_repository_implements_protocol(repo):
    assert isinstance(repo, GrowthRepository)


async def test_fake_repository_task_idempotency(repo):
    tenant_id, workspace_id = uuid4(), uuid4()
    task = NewTask(
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        pipeline="social",
        task_type="social.ingest",
        payload={},
        idempotency_key="ingest:1",
    )
    first = await repo.enqueue_task(task)
    second = await repo.enqueue_task(task)
    assert first == second
    assert len(repo.tasks_for("ingest:1")) == 1


async def test_fake_repository_rate_limit_is_all_or_nothing(repo, now):
    tenant_id = uuid4()
    checks = [
        RateLimitCheck(scope="global", scope_key="*", max_count=1, window_seconds=86400),
        RateLimitCheck(
            scope="platform", scope_key="reddit", max_count=1, window_seconds=86400
        ),
    ]
    assert (await repo.consume_rate_limits(tenant_id, checks, now=now)).allowed
    decision = await repo.consume_rate_limits(tenant_id, checks, now=now)
    assert decision.allowed is False
    assert decision.exceeded_scope == "global"


async def test_rate_limit_rolls_back_earlier_checks(repo, now):
    tenant_id = uuid4()
    checks = [
        RateLimitCheck(scope="global", scope_key="*", max_count=2, window_seconds=86400),
        RateLimitCheck(
            scope="platform", scope_key="reddit", max_count=1, window_seconds=86400
        ),
    ]
    assert (await repo.consume_rate_limits(tenant_id, checks, now=now)).allowed

    decision = await repo.consume_rate_limits(tenant_id, checks, now=now)
    assert decision.allowed is False
    assert decision.exceeded_scope == "platform"

    window_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    assert repo.counters[(tenant_id, "social", "global", "*", window_start)] == 1
    assert (
        repo.counters[(tenant_id, "social", "platform", "reddit", window_start)] == 1
    )


async def test_zero_max_count_denies_without_incrementing(repo, now):
    tenant_id = uuid4()
    check = RateLimitCheck(
        scope="global", scope_key="*", max_count=0, window_seconds=86400
    )

    decision = await repo.consume_rate_limits(tenant_id, [check], now=now)

    assert decision.allowed is False
    assert decision.exceeded_scope == "global"
    assert repo.counters == {}


async def test_claim_task_order_and_attempts(repo, now):
    tenant_id, workspace_id = uuid4(), uuid4()
    run_after = now - timedelta(minutes=1)
    await repo.enqueue_task(
        _task(tenant_id, workspace_id, "claim:low", run_after=run_after, priority=50)
    )
    high_id = await repo.enqueue_task(
        _task(tenant_id, workspace_id, "claim:high", run_after=run_after, priority=1)
    )

    claimed = await repo.claim_task("worker-1", now=now)

    assert claimed is not None
    assert claimed.id == high_id
    assert claimed.status == "running"
    assert claimed.locked_by == "worker-1"
    assert claimed.attempts == 0


async def test_complete_task_is_fenced(repo, now):
    tenant_id, workspace_id = uuid4(), uuid4()
    task_id = await repo.enqueue_task(
        _task(tenant_id, workspace_id, "complete:1", run_after=now - timedelta(minutes=1))
    )

    # A queued task is not completable.
    await repo.complete_task(task_id, worker_id="worker-1")
    assert repo.tasks[0].status == "queued"

    await repo.claim_task("worker-1", now=now)
    await repo.complete_task(task_id, worker_id="worker-2")
    assert repo.tasks[0].status == "running"

    await repo.complete_task(task_id, worker_id="worker-1")
    assert repo.tasks[0].status == "succeeded"
    assert repo.tasks[0].locked_by is None


async def test_fail_task_is_fenced_and_backs_off(repo, now):
    tenant_id, workspace_id = uuid4(), uuid4()
    task_id = await repo.enqueue_task(
        _task(
            tenant_id,
            workspace_id,
            "fail:1",
            run_after=now - timedelta(minutes=1),
            max_attempts=2,
        )
    )
    await repo.claim_task("worker-1", now=now)

    await repo.fail_task(task_id, "boom", now=now, worker_id="worker-2")
    assert repo.tasks[0].status == "running"
    assert repo.tasks[0].attempts == 0

    await repo.fail_task(task_id, "boom", now=now, worker_id="worker-1")
    row = repo.tasks[0]
    assert row.attempts == 1
    assert row.status == "queued"
    assert row.run_after == now + timedelta(seconds=60)

    await repo.claim_task("worker-1", now=row.run_after)
    second_fail_at = row.run_after
    await repo.fail_task(task_id, "boom again", now=second_fail_at, worker_id="worker-1")
    row = repo.tasks[0]
    assert row.attempts == 2
    assert row.status == "dead"
    assert row.locked_by is None


async def test_reclaim_stale_tasks_increments_attempts(repo, now):
    tenant_id, workspace_id = uuid4(), uuid4()
    await repo.enqueue_task(
        _task(tenant_id, workspace_id, "stale:1", run_after=now - timedelta(minutes=1))
    )
    claimed = await repo.claim_task("worker-1", now=now)
    assert claimed is not None

    reclaimed = await repo.reclaim_stale_tasks(60, now=now + timedelta(seconds=61))

    assert reclaimed == 1
    assert repo.tasks[0].status == "queued"
    assert repo.tasks[0].attempts == 1
    assert repo.tasks[0].locked_by is None


async def test_outbox_guards_and_idempotency(repo, now):
    tenant_id, workspace_id = uuid4(), uuid4()
    message = NewOutboxMessage(
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        topic="social.deliver",
        payload={},
        idempotency_key="outbox:1",
        next_attempt_at=now - timedelta(minutes=1),
    )
    first = await repo.enqueue_outbox(message)
    second = await repo.enqueue_outbox(message)
    assert first == second
    assert len(repo.outbox_for("outbox:1")) == 1

    # Only ``sending`` rows accept terminal writes.
    await repo.mark_outbox_sent(first)
    assert repo.outbox[0].status == "pending"

    claimed = await repo.claim_outbox(limit=10, now=now)
    assert [row.id for row in claimed] == [first]
    assert repo.outbox[0].status == "sending"

    await repo.mark_outbox_sent(first)
    assert repo.outbox[0].status == "sent"

    # A sent row can no longer be failed.
    await repo.mark_outbox_failed(first, "late failure", now=now)
    assert repo.outbox[0].status == "sent"
    assert repo.outbox[0].attempts == 0


async def test_outbox_failure_backs_off_and_dead_letters(repo, now):
    tenant_id, workspace_id = uuid4(), uuid4()
    outbox_id = await repo.enqueue_outbox(
        NewOutboxMessage(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            topic="social.deliver",
            payload={},
            idempotency_key="outbox:dead",
            next_attempt_at=now,
        )
    )

    clock = now
    for attempt in range(5):
        await repo.claim_outbox(limit=1, now=clock)
        row = repo.outbox[0]
        assert row.status == "sending"
        await repo.mark_outbox_failed(outbox_id, "boom", now=clock)
        row = repo.outbox[0]
        assert row.attempts == attempt + 1
        if attempt < 4:
            assert row.status == "failed"
            assert row.next_attempt_at == clock + timedelta(seconds=60 * 2**attempt)
            clock = row.next_attempt_at

    assert repo.outbox[0].status == "dead"
    assert repo.outbox[0].attempts == 5


async def test_lead_status_compare_and_set(repo):
    tenant_id, workspace_id = uuid4(), uuid4()
    lead, created = await repo.upsert_lead(
        NewSocialLead(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            platform="reddit",
            platform_post_id="abc",
            source_url="https://example.test/abc",
            dedupe_key="reddit:abc",
        )
    )
    assert created is True

    assert (
        await repo.update_lead_status(
            tenant_id, lead.id, expected_status="qualified", status="drafted"
        )
        is False
    )
    assert lead.status == "discovered"

    assert (
        await repo.update_lead_status(
            tenant_id, lead.id, expected_status="discovered", status="qualified"
        )
        is True
    )
    assert lead.status == "qualified"
    assert lead.version == 2


async def test_message_status_compare_and_set(repo):
    tenant_id, workspace_id = uuid4(), uuid4()
    message = await repo.create_message(
        NewOutreachMessage(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            channel="reddit",
            status="drafted",
            dedupe_key="message:1",
        )
    )

    assert (
        await repo.update_message_status(
            tenant_id, message.id, expected_status="approved", status="sent"
        )
        is False
    )
    assert (
        await repo.update_message_status(
            tenant_id, message.id, expected_status="drafted", status="sent"
        )
        is True
    )
    assert message.status == "sent"
    assert message.version == 2


async def test_approval_decision_is_single_shot(repo):
    tenant_id, workspace_id, message_id = uuid4(), uuid4(), uuid4()
    approval = await repo.create_approval_request(
        NewApprovalRequest(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            message_id=message_id,
            approval_id="approval:1",
        )
    )

    assert (
        await repo.decide_approval(tenant_id, approval.approval_id, "approved", "alice")
        is True
    )
    assert (
        await repo.decide_approval(tenant_id, approval.approval_id, "rejected", "bob")
        is False
    )
    assert approval.status == "approved"
    assert approval.decided_by == "alice"


async def test_truncate_all_for_tests_clears_every_store(repo):
    tenant_id, workspace_id = uuid4(), uuid4()
    await repo.enqueue_task(_task(tenant_id, workspace_id, "truncate:1"))
    repo.counters[(tenant_id, "social", "global", "*", datetime.now(timezone.utc))] = 1

    repo.truncate_all_for_tests()

    assert repo.tasks == []
    assert repo.outbox == []
    assert repo.counters == {}
