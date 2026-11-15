"""Tests for the growth task worker and transactional outbox dispatcher."""

import asyncio
from uuid import uuid4

import pytest

from growth_core.schemas import (
    NewApprovalRequest,
    NewOutboxMessage,
    NewTask,
)
from tests.growth.fakes import FakeGrowthRepository, FakeNotifier


async def _seed_task(
    repo: FakeGrowthRepository,
    *,
    task_type: str = "demo",
    idempotency_key: str = "demo:1",
    max_attempts: int = 5,
    run_after=None,
):
    tenant_id, workspace_id = uuid4(), uuid4()
    await repo.enqueue_task(
        NewTask(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            pipeline="social",
            task_type=task_type,
            payload={},
            idempotency_key=idempotency_key,
            max_attempts=max_attempts,
            run_after=run_after,
        )
    )
    return tenant_id, workspace_id


async def _seed_outbox(
    repo: FakeGrowthRepository,
    *,
    topic: str = "feishu.card",
    payload: dict | None = None,
    idempotency_key: str = "outbox:1",
    tenant_id=None,
    workspace_id=None,
    next_attempt_at=None,
):
    tenant_id = tenant_id or uuid4()
    workspace_id = workspace_id or uuid4()
    await repo.enqueue_outbox(
        NewOutboxMessage(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            topic=topic,
            payload=payload if payload is not None else {},
            idempotency_key=idempotency_key,
            next_attempt_at=next_attempt_at,
        )
    )
    return tenant_id, workspace_id


async def test_run_once_claims_and_completes(repo, now):
    from growth_core.services.worker import TaskRouter, run_once

    seen = []

    async def demo(task):
        seen.append(task)

    router = TaskRouter()
    router.register("demo", demo)
    await _seed_task(repo, idempotency_key="demo:1", run_after=now)
    assert await run_once(repo, router, worker_id="w1", now=now) is True
    assert len(seen) == 1
    assert await run_once(repo, router, worker_id="w1", now=now) is False
    task = repo.tasks_for("demo:1")[0]
    assert task.status == "succeeded"
    assert task.locked_by is None


async def test_handler_failure_is_recorded(repo, now):
    from growth_core.services.worker import TaskRouter, run_once

    async def boom(task):
        raise RuntimeError("boom")

    router = TaskRouter()
    router.register("demo", boom)
    await _seed_task(repo, idempotency_key="demo:2", max_attempts=2, run_after=now)
    assert await run_once(repo, router, worker_id="w1", now=now) is True
    task = repo.tasks_for("demo:2")[0]
    assert task.status == "queued"
    assert task.attempts == 1
    assert task.last_error == "RuntimeError: boom"


async def test_unknown_task_type_fails_with_no_handler(repo, now):
    from growth_core.services.worker import TaskRouter, run_once

    router = TaskRouter()
    await _seed_task(repo, task_type="mystery", idempotency_key="demo:3", run_after=now)
    assert await run_once(repo, router, worker_id="w1", now=now) is True
    task = repo.tasks_for("demo:3")[0]
    assert task.last_error == "ValueError: NO_HANDLER: mystery"
    assert task.attempts == 1


async def test_dead_lettering_task_is_still_reported_claimed(repo, now):
    from growth_core.services.worker import TaskRouter, run_once

    async def boom(task):
        raise RuntimeError("always")

    router = TaskRouter()
    router.register("demo", boom)
    await _seed_task(repo, idempotency_key="demo:4", max_attempts=1, run_after=now)
    assert await run_once(repo, router, worker_id="w1", now=now) is True
    task = repo.tasks_for("demo:4")[0]
    assert task.status == "dead"
    assert task.attempts == 1


async def test_run_forever_stops_after_current_iteration(repo):
    from growth_core.services.worker import TaskRouter, run_forever

    stop = asyncio.Event()
    seen = []

    async def demo(task):
        seen.append(task)
        stop.set()

    router = TaskRouter()
    router.register("demo", demo)
    await _seed_task(repo, idempotency_key="demo:5")
    await run_forever(
        repo, router, worker_id="w1", poll_seconds=0.01, stop=stop
    )
    assert len(seen) == 1
    assert repo.tasks_for("demo:5")[0].status == "succeeded"


async def test_run_forever_with_preset_stop_does_no_work(repo):
    from growth_core.services.worker import TaskRouter, run_forever

    stop = asyncio.Event()
    stop.set()
    seen = []

    async def demo(task):
        seen.append(task)

    router = TaskRouter()
    router.register("demo", demo)
    await _seed_task(repo, idempotency_key="demo:6")
    await run_forever(repo, router, worker_id="w1", poll_seconds=0.01, stop=stop)
    assert seen == []


async def test_run_forever_propagates_claim_errors(repo):
    from growth_core.services.worker import TaskRouter, run_forever

    class BrokenRepo(FakeGrowthRepository):
        async def claim_task(self, worker_id, now=None):
            raise ConnectionError("db down")

    with pytest.raises(ConnectionError):
        await run_forever(
            BrokenRepo(), TaskRouter(), worker_id="w1", poll_seconds=0.01
        )


async def test_dispatch_outbox_sends_feishu_card(repo, now):
    from growth_core.services.outbox import dispatch_outbox

    notifier = FakeNotifier()
    tenant_id, workspace_id = uuid4(), uuid4()
    await repo.create_approval_request(
        NewApprovalRequest(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            message_id=uuid4(),
            approval_id="approval-1",
        )
    )
    card = {"header": {"title": "Approve?"}}
    await _seed_outbox(
        repo,
        payload={"chat_id": "chat-1", "card": card, "approval_id": "approval-1"},
        next_attempt_at=now,
        tenant_id=tenant_id,
        workspace_id=workspace_id,
    )

    sent = await dispatch_outbox(repo, notifier, now=now)

    assert sent == 1
    assert notifier.calls == [("chat-1", card)]
    row = repo.outbox_for("outbox:1")[0]
    assert row.status == "sent"
    approval = await repo.get_approval_request(tenant_id, "approval-1")
    assert approval.external_id == "fake-1"


async def test_dispatch_outbox_records_notifier_failure(repo, now):
    from growth_core.services.outbox import dispatch_outbox

    class BrokenNotifier(FakeNotifier):
        async def send_card(self, chat_id, card):
            raise RuntimeError("feishu down")

    await _seed_outbox(
        repo,
        payload={"chat_id": "chat-1", "card": {}, "approval_id": "approval-1"},
        next_attempt_at=now,
    )
    sent = await dispatch_outbox(repo, BrokenNotifier(), now=now)

    assert sent == 0
    row = repo.outbox_for("outbox:1")[0]
    assert row.status == "failed"
    assert row.attempts == 1
    assert row.last_error == "RuntimeError: feishu down"


async def test_dispatch_outbox_unsupported_topic(repo, now):
    from growth_core.services.outbox import dispatch_outbox

    notifier = FakeNotifier()
    await _seed_outbox(
        repo, topic="sms.text", payload={"body": "hi"}, next_attempt_at=now
    )

    sent = await dispatch_outbox(repo, notifier, now=now)

    assert sent == 0
    assert notifier.calls == []
    row = repo.outbox_for("outbox:1")[0]
    assert row.status == "failed"
    assert row.last_error == "unsupported topic"


async def test_dispatch_outbox_malformed_payload(repo, now):
    from growth_core.services.outbox import dispatch_outbox

    notifier = FakeNotifier()
    await _seed_outbox(
        repo, payload={"chat_id": "chat-1", "card": {}}, next_attempt_at=now
    )

    sent = await dispatch_outbox(repo, notifier, now=now)

    assert sent == 0
    assert notifier.calls == []
    row = repo.outbox_for("outbox:1")[0]
    assert row.status == "failed"
    assert row.last_error == "ValueError: malformed feishu.card payload: missing approval_id"


async def test_dispatch_outbox_honors_limit(repo, now):
    from growth_core.services.outbox import dispatch_outbox

    notifier = FakeNotifier()
    for index in range(3):
        await _seed_outbox(
            repo,
            payload={"chat_id": "c", "card": {}, "approval_id": f"a-{index}"},
            idempotency_key=f"outbox:{index}",
            next_attempt_at=now,
        )

    sent = await dispatch_outbox(repo, notifier, limit=2, now=now)

    assert sent == 2
    assert len(notifier.calls) == 2
    statuses = [row.status for row in repo.outbox]
    assert statuses.count("sent") == 2
    assert statuses.count("pending") == 1


async def test_dispatch_outbox_sets_external_id_before_marking_sent(repo, now):
    from growth_core.services.outbox import dispatch_outbox

    order = []

    class RecordingRepo(FakeGrowthRepository):
        async def set_approval_external_id(self, tenant_id, approval_id, external_id):
            order.append("external_id")
            await super().set_approval_external_id(
                tenant_id, approval_id, external_id
            )

        async def mark_outbox_sent(self, outbox_id):
            order.append("sent")
            await super().mark_outbox_sent(outbox_id)

    recording = RecordingRepo()
    await _seed_outbox(
        recording,
        payload={"chat_id": "c", "card": {}, "approval_id": "a-1"},
        next_attempt_at=now,
    )

    assert await dispatch_outbox(recording, FakeNotifier(), now=now) == 1
    assert order == ["external_id", "sent"]
