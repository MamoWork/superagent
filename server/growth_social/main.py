"""Application factory for the social Growth Agent module.

This module intentionally defines no module-level ``app``; the runtime
entrypoint is added separately so tests and workers can build an app with
injected dependencies.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI

from growth_core.api import core
from growth_core.config import GrowthSettings
from growth_core.repositories.base import GrowthRepository

from growth_social.api import router as social_router


def create_social_app(
    *,
    settings: GrowthSettings,
    repo: GrowthRepository,
    adapters: Any | None = None,
    notifier: Any | None = None,
    llm: Any | None = None,
) -> FastAPI:
    """Build the social API app and store its dependencies on ``app.state``.

    ``adapters``, ``notifier``, and ``llm`` are forward-compatible runtime
    dependencies; their concrete protocol types arrive in later tasks.
    """
    app = FastAPI(title="Growth Agent Social API", version="0.1.0")
    app.state.settings = settings
    app.state.repo = repo
    app.state.adapters = adapters
    app.state.notifier = notifier
    app.state.llm = llm

    app.include_router(core.router)
    app.include_router(social_router)
    return app
