from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response

from app.schemas import Run, Schedule, ScheduleCreate, ScheduleUpdate
from app.services.scheduler import SchedulerService

router = APIRouter(prefix="/api/v1/schedules", tags=["schedules"])


def _service(request: Request) -> SchedulerService:
    return request.app.state.scheduler_service


@router.get("")
async def list_schedules(request: Request) -> dict:
    return {"schedules": _service(request).list()}


@router.post("", response_model=Schedule, status_code=201)
async def create_schedule(payload: ScheduleCreate, request: Request) -> Schedule:
    try:
        return _service(request).add(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{schedule_id}", response_model=Schedule)
async def get_schedule(schedule_id: str, request: Request) -> Schedule:
    schedule = _service(request).get(schedule_id)
    if schedule is None:
        raise HTTPException(status_code=404, detail="定时任务不存在")
    return schedule


@router.patch("/{schedule_id}", response_model=Schedule)
async def update_schedule(
    schedule_id: str,
    payload: ScheduleUpdate,
    request: Request,
) -> Schedule:
    try:
        schedule = _service(request).update(schedule_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if schedule is None:
        raise HTTPException(status_code=404, detail="定时任务不存在")
    return schedule


@router.delete("/{schedule_id}", status_code=204)
async def delete_schedule(schedule_id: str, request: Request) -> Response:
    if not _service(request).delete(schedule_id):
        raise HTTPException(status_code=404, detail="定时任务不存在")
    return Response(status_code=204)


@router.post("/{schedule_id}/run", response_model=Run)
async def run_schedule_now(schedule_id: str, request: Request) -> Run:
    service = _service(request)
    if service.get(schedule_id) is None:
        raise HTTPException(status_code=404, detail="定时任务不存在")
    run = await service.run_now(schedule_id)
    if run is None:
        raise HTTPException(
            status_code=400,
            detail="任务未启用或执行失败；请查看 last_error 或服务日志。",
        )
    return run
