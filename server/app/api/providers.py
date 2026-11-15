from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

router = APIRouter(prefix="/api/v1/providers", tags=["providers"])


@router.get("")
async def list_providers(request: Request) -> dict:
    registry = request.app.state.registry
    return {"providers": [provider.model_dump() for provider in registry.list()]}


@router.get("/health")
async def all_provider_health(request: Request) -> dict:
    registry = request.app.state.registry
    health = await registry.health()
    return {"providers": [item.model_dump() for item in health]}


@router.get("/{provider_id}/health")
async def provider_health(provider_id: str, request: Request) -> dict:
    registry = request.app.state.registry
    try:
        provider = registry.get(provider_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return (await provider.health()).model_dump()
