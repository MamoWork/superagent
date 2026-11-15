from __future__ import annotations

import hashlib

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import PlainTextResponse

from app.schemas import (
    AnalysisRequest,
    ManualSignalCreate,
    OpportunityAnalysis,
    Run,
    RunCreate,
    Signal,
)
from app.services.analysis import brief_markdown, build_brief
from app.services.analyzer import (
    AnalysisError,
    AnalysisNotConfigured,
    analyze_run,
    analysis_markdown,
    build_engine,
)
from app.services.runs import execute_run, get_run_detail

router = APIRouter(prefix="/api/v1/runs", tags=["runs"])


@router.post("", response_model=Run)
async def create_run(payload: RunCreate, request: Request) -> Run:
    try:
        return await execute_run(
            request.app.state.db,
            request.app.state.registry,
            payload,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("")
async def list_runs(request: Request, limit: int = 50) -> dict:
    db = request.app.state.db
    runs = db.list_runs(limit=max(1, min(limit, 200)))
    analyzed = db.run_ids_with_analysis([run["id"] for run in runs])
    return {
        "runs": [
            Run(
                **run,
                signals=[],
                has_analysis=run["id"] in analyzed,
            ).model_dump(exclude={"signals"})
            for run in runs
        ]
    }


@router.get("/{run_id}", response_model=Run)
async def get_run(run_id: str, request: Request) -> Run:
    run = get_run_detail(request.app.state.db, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run 不存在")
    return run


@router.get("/{run_id}/signals")
async def get_run_signals(run_id: str, request: Request) -> dict:
    db = request.app.state.db
    if db.get_run(run_id) is None:
        raise HTTPException(status_code=404, detail="Run 不存在")
    return {"signals": [signal.model_dump() for signal in db.get_signals(run_id)]}


@router.post("/{run_id}/signals", response_model=Signal)
async def add_manual_signal(
    run_id: str,
    payload: ManualSignalCreate,
    request: Request,
) -> Signal:
    db = request.app.state.db
    if db.get_run(run_id) is None:
        raise HTTPException(status_code=404, detail="Run 不存在")
    signal_id = hashlib.sha256(
        f"{payload.provider_id}|{payload.source_url}|{payload.title}".encode("utf-8")
    ).hexdigest()[:24]
    signal = Signal(
        id=signal_id,
        provider_id=payload.provider_id,
        source_type=payload.source_type,
        source_url=payload.source_url,
        title=payload.title,
        quote=payload.quote,
        author_public=payload.author_public,
        published_at=payload.published_at,
        metrics=payload.metrics,
    )
    db.add_signals(run_id, [signal])
    return signal


@router.get("/{run_id}/brief", response_class=PlainTextResponse)
async def get_brief(run_id: str, request: Request) -> PlainTextResponse:
    run = get_run_detail(request.app.state.db, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run 不存在")
    brief = build_brief(run)
    return PlainTextResponse(
        brief_markdown(run, brief),
        media_type="text/markdown; charset=utf-8",
    )


def _resolve_engine(request: Request, model_override: str | None):
    if model_override:
        return build_engine(request.app.state.settings, model_override)
    if request.app.state.analysis_engine is not None:
        return request.app.state.analysis_engine
    return build_engine(request.app.state.settings)


@router.post("/{run_id}/analyze", response_model=OpportunityAnalysis)
async def analyze(
    run_id: str,
    request: Request,
    payload: AnalysisRequest | None = None,
) -> OpportunityAnalysis:
    run = get_run_detail(request.app.state.db, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run 不存在")
    try:
        engine = _resolve_engine(request, payload.model if payload else None)
    except AnalysisNotConfigured as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if engine is None:
        raise HTTPException(
            status_code=400,
            detail=(
                "未配置 AI 模型。设置 OPPORTUNITY_AI_MODEL，可选 "
                "OPPORTUNITY_AI_BASE_URL / OPPORTUNITY_AI_API_KEY。"
            ),
        )
    try:
        return await analyze_run(
            request.app.state.db,
            run,
            engine,
            timeout=request.app.state.settings.ai_timeout + 30,
        )
    except AnalysisError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/{run_id}/analysis", response_model=OpportunityAnalysis)
async def get_analysis(run_id: str, request: Request) -> OpportunityAnalysis:
    db = request.app.state.db
    if db.get_run(run_id) is None:
        raise HTTPException(status_code=404, detail="Run 不存在")
    data = db.get_analysis(run_id)
    if data is None:
        raise HTTPException(status_code=404, detail="该 Run 还没有 AI 分析")
    return OpportunityAnalysis(**data)


@router.get("/{run_id}/analysis.md", response_class=PlainTextResponse)
async def get_analysis_markdown(run_id: str, request: Request) -> PlainTextResponse:
    db = request.app.state.db
    run = get_run_detail(db, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run 不存在")
    data = db.get_analysis(run_id)
    if data is None:
        raise HTTPException(status_code=404, detail="该 Run 还没有 AI 分析")
    analysis = OpportunityAnalysis(**data)
    return PlainTextResponse(
        analysis_markdown(run, analysis),
        media_type="text/markdown; charset=utf-8",
    )
