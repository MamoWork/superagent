from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response

from app.schemas import (
    SavedOpportunity,
    SavedOpportunityCreate,
    SavedOpportunityUpdate,
)
from app.services.library import (
    LibraryAnalysisMissing,
    LibraryRunNotFound,
    delete_saved,
    get_saved,
    list_saved,
    save_opportunity,
    update_saved,
)

router = APIRouter(prefix="/api/v1/library", tags=["library"])


@router.get("")
async def list_library(request: Request) -> dict:
    return {
        "opportunities": [
            item.model_dump() for item in list_saved(request.app.state.db)
        ]
    }


@router.post("", response_model=SavedOpportunity, status_code=201)
async def save_to_library(
    payload: SavedOpportunityCreate, request: Request
) -> SavedOpportunity:
    try:
        return save_opportunity(
            request.app.state.db,
            payload.run_id,
            stage=payload.stage,
            notes=payload.notes,
        )
    except LibraryRunNotFound as exc:
        raise HTTPException(status_code=404, detail="Run 不存在") from exc
    except LibraryAnalysisMissing as exc:
        raise HTTPException(
            status_code=409,
            detail="该 Run 还没有 AI 分析，无法保存到机会库。",
        ) from exc


@router.get("/{run_id}", response_model=SavedOpportunity)
async def get_library_item(run_id: str, request: Request) -> SavedOpportunity:
    item = get_saved(request.app.state.db, run_id)
    if item is None:
        raise HTTPException(status_code=404, detail="机会库中没有该记录")
    return item


@router.patch("/{run_id}", response_model=SavedOpportunity)
async def update_library_item(
    run_id: str, payload: SavedOpportunityUpdate, request: Request
) -> SavedOpportunity:
    item = update_saved(
        request.app.state.db,
        run_id,
        stage=payload.stage,
        notes=payload.notes,
    )
    if item is None:
        raise HTTPException(status_code=404, detail="机会库中没有该记录")
    return item


@router.delete("/{run_id}", status_code=204)
async def delete_library_item(run_id: str, request: Request) -> Response:
    if not delete_saved(request.app.state.db, run_id):
        raise HTTPException(status_code=404, detail="机会库中没有该记录")
    return Response(status_code=204)
