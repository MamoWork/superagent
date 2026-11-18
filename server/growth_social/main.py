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
    repo: GrowthRepository | None = None,
    adapters: Any | None = None,
    notifier: Any | None = None,
    llm: Any | None = None,
    lifespan: Any | None = None,
) -> FastAPI:
    """Build the social API app and store its dependencies on ``app.state``.

    ``repo`` is optional because the Postgres pool cannot be created at import
    time: ``growth_social.asgi`` connects inside the passed ``lifespan`` and
    writes the live dependencies onto ``app.state`` before serving. OpenAPI
    documents are disabled; this is an internal service.
    """
    app = FastAPI(
        title="Growth Agent Social API",
        version="0.1.0",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.repo = repo
    app.state.adapters = adapters
    app.state.notifier = notifier
    app.state.llm = llm

    app.include_router(core.router)
    app.include_router(social_router)
    return app


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("growth_social.asgi:app", host="0.0.0.0", port=8780)
