"""ASGI entrypoint for the social Growth Agent API.

The Postgres pool cannot be created at import time, so the module-level
``app`` is built with a lifespan that connects on startup, attaches the live
repository/adapters/notifier/llm to ``app.state``, and closes the repository on
shutdown. Serve it with ``uvicorn growth_social.asgi:app`` or
``python -m growth_social.main``.

Tests never import this module; they use :func:`create_social_app` directly
with an in-memory repository.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI

# Adapter factories register on import; the app never references them directly.
from growth_core.adapters import feishu as _feishu  # noqa: F401
from growth_core.adapters import llm as _llm  # noqa: F401
from growth_core.config import GrowthSettings
from growth_core.repositories.postgres import PostgresGrowthRepository
from growth_social.adapters import hackernews as _hackernews  # noqa: F401
from growth_social.adapters import reddit as _reddit  # noqa: F401
from growth_social.handlers import build_social_adapters
from growth_social.main import create_social_app

__all__ = ["app", "lifespan"]


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Connect the repository and build adapters for the app's lifetime."""
    settings: GrowthSettings = app.state.settings
    repo = await PostgresGrowthRepository.connect(settings.database_url)
    try:
        registry, adapters = await build_social_adapters(repo, settings)
        app.state.repo = repo
        app.state.registry = registry
        app.state.adapters = adapters
        app.state.notifier = registry.notifier()
        app.state.llm = registry.llm()
        yield
    finally:
        await repo.close()


app = create_social_app(
    settings=GrowthSettings.from_env(),
    lifespan=lifespan,
)
