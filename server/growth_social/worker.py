"""Composition root for the social Growth Agent worker.

Run with ``python -m growth_social.worker``. The module imports every adapter
package so their factories register before :class:`AdapterRegistry` resolves
them, then connects the repository, builds the router, and runs the shared
task/outbox loop until the process is stopped.

This entrypoint never posts, comments, or DMs. Feishu cards leave through the
transactional outbox, and the service logs nothing about secrets.
"""

from __future__ import annotations

import asyncio

# Adapter factories register on import; the worker never references them
# directly, so keep the imports for their side effects.
from growth_core.adapters import feishu as _feishu  # noqa: F401
from growth_core.adapters import llm as _llm  # noqa: F401
from growth_core.config import GrowthSettings
from growth_core.repositories.postgres import PostgresGrowthRepository
from growth_core.services.worker import run_worker_loop
from growth_social.adapters import hackernews as _hackernews  # noqa: F401
from growth_social.adapters import reddit as _reddit  # noqa: F401
from growth_social.handlers import build_social_adapters, build_social_router

__all__ = ["main"]


async def main() -> None:
    """Wire the real dependencies and run the task/outbox loop forever."""
    settings = GrowthSettings.from_env()
    repo = await PostgresGrowthRepository.connect(settings.database_url)
    try:
        registry, adapters = await build_social_adapters(repo, settings)
        notifier = registry.notifier()
        llm = registry.llm()
        router = build_social_router(
            repo=repo,
            adapters=adapters,
            notifier=notifier,
            llm=llm,
            settings=settings,
        )
        await run_worker_loop(
            repo=repo,
            router=router,
            notifier=notifier,
            worker_id=settings.worker_id,
            poll_seconds=settings.worker_poll_seconds,
        )
    finally:
        await repo.close()


if __name__ == "__main__":
    asyncio.run(main())
