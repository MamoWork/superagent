from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.domain_packs import get_pack, list_packs

router = APIRouter(prefix="/api/v1/domain-packs", tags=["domain-packs"])


@router.get("")
async def list_domain_packs() -> dict:
    return {"domain_packs": [pack.to_dict() for pack in list_packs()]}


@router.get("/{pack_id}")
async def get_domain_pack(pack_id: str) -> dict:
    try:
        return get_pack(pack_id).to_dict()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
