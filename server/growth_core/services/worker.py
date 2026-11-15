"""Task worker loop for the Growth Agent pipeline.

``TaskRouter`` maps a task type to an async handler. ``run_once`` claims a
single queued task, dispatches it, and records success or failure through the
repository. ``run_forever`` repeats ``run_once`` until a stop event is set.

Repository errors (claim, completion, failure recording) are intentionally not
swallowed: they propagate so a supervisor or crash loop can react instead of
the worker spinning silently.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import datetime

from growth_core.repositories.base import GrowthRepository
from growth_core.schemas import PipelineTask

__all__ = [
    "TaskHandler",
    "TaskRouter",
    "run_forever",
    "run_once",
]

TaskHandler = Callable[[PipelineTask], Awaitable[None]]


class TaskRouter:
    """Dispatch pipeline tasks to handlers registered by task type."""

    def __init__(self) -> None:
        self._handlers: dict[str, TaskHandler] = {}

    def register(self, task_type: str, handler: TaskHandler) -> None:
        self._handlers[task_type] = handler

    async def handle(self, task: PipelineTask) -> None:
        handler = self._handlers.get(task.task_type)
        if handler is None:
            raise ValueError(f"NO_HANDLER: {task.task_type}")
        await handler(task)


async def run_once(
    repo: GrowthRepository,
    router: TaskRouter,
    *,
    worker_id: str,
    now: datetime | None = None,
) -> bool:
    """Claim and process at most one task.

    Returns ``True`` when a task was claimed (whether it succeeded or failed)
    and ``False`` when the queue had nothing claimable. A task that
    dead-letters is still reported as claimed.
    """
    task = await repo.claim_task(worker_id, now=now)
    if task is None:
        return False

    try:
        await router.handle(task)
    except Exception as exc:  # noqa: BLE001 - recorded, then next task
        await repo.fail_task(
            task.id,
            f"{type(exc).__name__}: {exc}",
            now=now,
            worker_id=task.locked_by,
        )
    else:
        await repo.complete_task(task.id, task.locked_by)
    return True


async def run_forever(
    repo: GrowthRepository,
    router: TaskRouter,
    *,
    worker_id: str,
    poll_seconds: float = 2.0,
    stop: asyncio.Event | None = None,
) -> None:
    """Poll the queue forever, sleeping ``poll_seconds`` whenever it is idle.

    Returns once ``stop`` is set. With ``stop=None`` the loop never exits.
    Repository errors are not caught here; they propagate to the caller.
    """
    while True:
        if stop is not None and stop.is_set():
            return
        did_work = await run_once(repo, router, worker_id=worker_id)
        if stop is not None and stop.is_set():
            return
        if not did_work:
            await asyncio.sleep(poll_seconds)
