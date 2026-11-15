"""HTTP routes for the social Growth Agent module."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from growth_core.api.deps import RequestContext, get_context, require_service_token
from growth_core.schemas import NewTask

router = APIRouter(dependencies=[Depends(require_service_token)])


class LeadTaskRequest(BaseModel):
    lead_id: UUID


def _clamp_limit(limit: int) -> int:
    return max(1, min(200, limit))


async def _enqueue(
    request: Request,
    ctx: RequestContext,
    task_type: str,
    payload: dict[str, object],
    idempotency_key: str,
) -> dict[str, str]:
    task_id = await request.app.state.repo.enqueue_task(
        NewTask(
            tenant_id=ctx.tenant_id,
            workspace_id=ctx.workspace_id,
            pipeline="social",
            task_type=task_type,
            payload=payload,
            idempotency_key=idempotency_key,
        )
    )
    return {"task_id": str(task_id)}


@router.post("/internal/v1/social/ingest")
async def ingest(
    request: Request, ctx: RequestContext = Depends(get_context)
) -> dict[str, str]:
    if not ctx.idempotency_key:
        raise HTTPException(
            status_code=400, detail={"code": "INVALID_IDEMPOTENCY_KEY"}
        )
    return await _enqueue(
        request, ctx, "social.ingest", {}, ctx.idempotency_key
    )


@router.post("/internal/v1/social/score")
async def score(
    body: LeadTaskRequest,
    request: Request,
    ctx: RequestContext = Depends(get_context),
) -> dict[str, str]:
    return await _enqueue(
        request,
        ctx,
        "social.score",
        {"lead_id": str(body.lead_id)},
        f"score:{body.lead_id}",
    )


@router.post("/internal/v1/social/draft")
async def draft(
    body: LeadTaskRequest,
    request: Request,
    ctx: RequestContext = Depends(get_context),
) -> dict[str, str]:
    return await _enqueue(
        request,
        ctx,
        "social.draft",
        {"lead_id": str(body.lead_id)},
        f"draft:{body.lead_id}",
    )


@router.get("/api/growth/social/leads")
async def list_leads(
    request: Request,
    status: str | None = Query(default=None),
    limit: int = Query(default=50),
    ctx: RequestContext = Depends(get_context),
) -> list[dict[str, object]]:
    rows = await request.app.state.repo.list_leads(
        ctx.tenant_id,
        status=status or None,
        limit=_clamp_limit(limit),
    )
    return [row.model_dump(mode="json") for row in rows]


@router.get("/api/growth/social/messages")
async def list_messages(
    request: Request,
    status: str | None = Query(default=None),
    limit: int = Query(default=50),
    ctx: RequestContext = Depends(get_context),
) -> list[dict[str, object]]:
    rows = await request.app.state.repo.list_messages(
        ctx.tenant_id,
        status=status or None,
        limit=_clamp_limit(limit),
    )
    return [row.model_dump(mode="json") for row in rows]
