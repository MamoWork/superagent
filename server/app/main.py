from __future__ import annotations

import html as html_lib
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    Response,
)
from fastapi.staticfiles import StaticFiles

from app.api import ai, domain_packs, library, providers, runs, schedules
from app.config import Settings
from app.db import Database
from app.providers.registry import ProviderRegistry, build_registry
from app.services.analyzer import AnalysisEngine
from app.services.scheduler import SchedulerService
from app.ui import (
    assets_dir,
    inject_runtime_config,
    read_index_html,
    resolve_web_dist,
    web_dist_candidates,
)


def _missing_ui_html(searched: list[Path]) -> str:
    paths = "\n".join(html_lib.escape(str(path)) for path in searched)
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>Opportunity Scout · 前端未构建</title></head>
<body style="font:14px -apple-system,BlinkMacSystemFont,sans-serif;padding:40px;line-height:1.6">
<h1>前端尚未构建</h1>
<p>后端已启动，但没有找到 <code>index.html</code>。请先构建 Web 前端：</p>
<pre style="background:#f4f5f7;padding:16px;border-radius:8px">cd web
npm install
npm run build</pre>
<p>已查找：</p><pre style="background:#f4f5f7;padding:16px;border-radius:8px">{paths}</pre>
<p>API 文档仍在 <a href="/docs">/docs</a>。</p>
</body></html>"""


def create_app(
    settings: Settings | None = None,
    registry: ProviderRegistry | None = None,
    analysis_engine: AnalysisEngine | None = None,
    scheduler_service: SchedulerService | None = None,
    cors_origins: list[str] | None = None,
) -> FastAPI:
    settings = settings or Settings()
    db = Database(settings.db_path)
    db.init()
    registry = registry or build_registry(settings)
    web_dist = resolve_web_dist(settings.web_dist_dir)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        service = app.state.scheduler_service
        if settings.scheduler_enabled:
            service.start()
        try:
            yield
        finally:
            service.shutdown()

    app = FastAPI(
        title="Opportunity Scout API",
        version="0.1.0",
        description=(
            "Local-first opportunity research API. Data sources are isolated "
            "behind provider adapters; the core never calls a CLI directly."
        ),
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.db = db
    app.state.registry = registry
    app.state.analysis_engine = analysis_engine
    app.state.desktop = False
    app.state.desktop_token = None
    app.state.web_dist = web_dist
    app.state.scheduler_service = scheduler_service or SchedulerService(
        db, registry, settings, analysis_engine
    )

    def index_response() -> HTMLResponse:
        index_html = read_index_html(web_dist)
        if index_html is None:
            return HTMLResponse(
                _missing_ui_html(web_dist_candidates(settings.web_dist_dir)),
                status_code=404,
                headers={"Cache-Control": "no-store"},
            )
        return HTMLResponse(
            inject_runtime_config(
                index_html,
                desktop_token=getattr(app.state, "desktop_token", None),
            ),
            headers={"Cache-Control": "no-store"},
        )

    @app.middleware("http")
    async def cache_control(request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/assets/") and response.status_code == 200:
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        elif response.headers.get("content-type", "").startswith("text/html"):
            response.headers.setdefault("Cache-Control", "no-store")
        return response

    @app.get("/", include_in_schema=False, response_model=None)
    async def root():
        return index_response()

    @app.get("/index.html", include_in_schema=False, response_model=None)
    async def index_file():
        return index_response()

    @app.get("/favicon.ico", include_in_schema=False)
    async def favicon() -> Response:
        return Response(status_code=204)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins or ["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/v1/health", tags=["meta"])
    async def health() -> dict:
        return {
            "ok": True,
            "service": "opportunity-scout-api",
            "version": "0.1.0",
            "providers": app.state.registry.ids(),
        }

    @app.get("/api/v1/app/info", tags=["meta"])
    async def app_info() -> dict:
        return {
            "desktop": bool(getattr(app.state, "desktop", False)),
            "version": "0.1.0",
            "db_path": str(settings.db_path),
            "data_dir": str(settings.db_path.parent),
            "ui_available": web_dist is not None,
        }

    static_assets = assets_dir(web_dist)
    if static_assets is not None:
        app.mount(
            "/assets",
            StaticFiles(directory=str(static_assets)),
            name="assets",
        )

    app.include_router(ai.router)
    app.include_router(domain_packs.router)
    app.include_router(library.router)
    app.include_router(providers.router)
    app.include_router(runs.router)
    app.include_router(schedules.router)

    @app.get("/{full_path:path}", include_in_schema=False, response_model=None)
    async def spa_fallback(full_path: str):
        if full_path == "api" or full_path.startswith("api/"):
            return JSONResponse({"detail": "Not Found"}, status_code=404)
        if web_dist is None:
            return index_response()
        root = web_dist.resolve()
        candidate = (root / full_path).resolve()
        if candidate.is_file() and candidate.is_relative_to(root):
            return FileResponse(candidate)
        if Path(full_path).suffix:
            return JSONResponse({"detail": "Not Found"}, status_code=404)
        return index_response()

    return app


app = create_app()
