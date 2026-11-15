from __future__ import annotations

from fastapi import APIRouter, Request

from app.schemas import AIStatus
from app.services.analyzer import ai_status

router = APIRouter(prefix="/api/v1/ai", tags=["ai"])


@router.get("/status", response_model=AIStatus)
async def get_ai_status(request: Request) -> AIStatus:
    return ai_status(request.app.state.settings)
