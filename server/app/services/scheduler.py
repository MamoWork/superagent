from __future__ import annotations

import logging
import uuid
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config import Settings
from app.db import Database, utcnow
from app.domain_packs import get_pack
from app.providers.registry import ProviderRegistry
from app.schemas import (
    Run,
    RunCreate,
    Schedule,
    ScheduleCreate,
    ScheduleUpdate,
)
from app.services.analyzer import (
    AnalysisEngine,
    AnalysisError,
    analyze_run,
    build_engine,
)
from app.services.runs import execute_run

logger = logging.getLogger(__name__)


def validate_cron(expression: str) -> str:
    expression = expression.strip()
    if not expression:
        raise ValueError("cron 不能为空。")
    try:
        CronTrigger.from_crontab(expression)
    except ValueError as exc:
        raise ValueError(
            f"cron 格式不正确：{expression}。请使用 5 段格式，例如 `0 9 * * *`。"
        ) from exc
    return expression


class SchedulerService:
    """Local in-process scheduler backed by APScheduler.

    Schedule definitions live in SQLite; APScheduler only holds the runtime
    jobs. On startup every enabled schedule is re-registered, so a restart does
    not lose the user's schedules.
    """

    def __init__(
        self,
        db: Database,
        registry: ProviderRegistry,
        settings: Settings,
        analysis_engine: AnalysisEngine | None = None,
    ) -> None:
        kwargs = {}
        if settings.scheduler_timezone:
            kwargs["timezone"] = settings.scheduler_timezone
        self.db = db
        self.registry = registry
        self.settings = settings
        self.analysis_engine = analysis_engine
        self.scheduler = AsyncIOScheduler(**kwargs)
        self._started = False

    def start(self) -> None:
        if self._started:
            return
        self.scheduler.start()
        self._started = True
        for schedule in self.db.list_schedules():
            if not schedule["enabled"]:
                continue
            try:
                validate_cron(schedule["cron"])
                self._add_job(schedule["id"])
            except ValueError:
                logger.warning("跳过 cron 无效的定时任务：%s", schedule["id"])

    def shutdown(self) -> None:
        if self._started and self.scheduler.running:
            self.scheduler.shutdown(wait=False)
        self._started = False

    def _add_job(self, schedule_id: str) -> None:
        schedule = self.db.get_schedule(schedule_id)
        if schedule is None or not schedule["enabled"]:
            return
        self.scheduler.add_job(
            self._run_schedule,
            trigger=CronTrigger.from_crontab(schedule["cron"]),
            id=schedule_id,
            args=[schedule_id],
            replace_existing=True,
            max_instances=1,
            coalesce=True,
            misfire_grace_time=3600,
        )

    def _sync_job(self, schedule_id: str) -> None:
        if not self._started:
            return
        if self.scheduler.get_job(schedule_id):
            self.scheduler.remove_job(schedule_id)
        schedule = self.db.get_schedule(schedule_id)
        if schedule and schedule["enabled"]:
            self._add_job(schedule_id)

    def _validate_target(self, provider_ids: list[str], domain_pack: str) -> None:
        unknown = [pid for pid in provider_ids if pid not in self.registry.ids()]
        if unknown:
            raise ValueError(f"未知数据源：{', '.join(unknown)}")
        try:
            get_pack(domain_pack)
        except KeyError as exc:
            raise ValueError(str(exc)) from exc

    def _to_schedule(self, schedule: dict) -> Schedule:
        return Schedule(**schedule, next_run_at=self._next_run_at(schedule))

    def _next_run_at(self, schedule: dict) -> str | None:
        job = self.scheduler.get_job(schedule["id"]) if self._started else None
        if job and job.next_run_time:
            return job.next_run_time.isoformat()
        if not schedule["enabled"]:
            return None
        try:
            trigger = CronTrigger.from_crontab(schedule["cron"])
            now = datetime.now(trigger.timezone)
            next_fire = trigger.get_next_fire_time(None, now)
            return next_fire.isoformat() if next_fire else None
        except (ValueError, TypeError):
            return None

    def list(self) -> list[Schedule]:
        return [self._to_schedule(item) for item in self.db.list_schedules()]

    def get(self, schedule_id: str) -> Schedule | None:
        schedule = self.db.get_schedule(schedule_id)
        return self._to_schedule(schedule) if schedule else None

    def add(self, payload: ScheduleCreate) -> Schedule:
        cron = validate_cron(payload.cron)
        self._validate_target(payload.provider_ids, payload.domain_pack)
        schedule_id = f"sch_{uuid.uuid4().hex[:12]}"
        self.db.create_schedule(
            {
                "id": schedule_id,
                "workspace_id": payload.workspace_id,
                "name": payload.name,
                "domain_pack": payload.domain_pack,
                "direction": payload.direction,
                "keywords": payload.keywords,
                "provider_ids": list(dict.fromkeys(payload.provider_ids)),
                "limit_per_provider": payload.limit_per_provider,
                "time_range_days": payload.time_range_days,
                "cron": cron,
                "enabled": payload.enabled,
                "created_at": utcnow(),
            }
        )
        if self._started:
            self._sync_job(schedule_id)
        schedule = self.get(schedule_id)
        assert schedule is not None
        return schedule

    def update(self, schedule_id: str, payload: ScheduleUpdate) -> Schedule | None:
        if self.db.get_schedule(schedule_id) is None:
            return None
        fields = payload.model_dump(exclude_unset=True)
        if "cron" in fields:
            fields["cron"] = validate_cron(fields["cron"])
        if "provider_ids" in fields:
            fields["provider_ids"] = list(dict.fromkeys(fields["provider_ids"]))
        if "provider_ids" in fields or "domain_pack" in fields:
            current = self.db.get_schedule(schedule_id)
            assert current is not None
            self._validate_target(
                fields.get("provider_ids", current["provider_ids"]),
                fields.get("domain_pack", current["domain_pack"]),
            )
        self.db.update_schedule(schedule_id, **fields)
        self._sync_job(schedule_id)
        return self.get(schedule_id)

    def delete(self, schedule_id: str) -> bool:
        if self._started and self.scheduler.get_job(schedule_id):
            self.scheduler.remove_job(schedule_id)
        return self.db.delete_schedule(schedule_id)

    async def run_now(self, schedule_id: str) -> Run | None:
        return await self._run_schedule(schedule_id)

    async def _run_schedule(self, schedule_id: str) -> Run | None:
        schedule = self.db.get_schedule(schedule_id)
        if schedule is None or not schedule["enabled"]:
            return None
        payload = RunCreate(
            workspace_id=schedule["workspace_id"],
            domain_pack=schedule["domain_pack"],
            direction=schedule["direction"],
            keywords=schedule["keywords"],
            provider_ids=schedule["provider_ids"],
            limit_per_provider=schedule["limit_per_provider"],
            time_range_days=schedule["time_range_days"],
        )
        try:
            run = await execute_run(self.db, self.registry, payload)
        except Exception as exc:  # a broken schedule must not kill the scheduler
            logger.exception("定时任务执行失败：%s", schedule_id)
            self.db.mark_schedule_run(schedule_id, run_id="", error=str(exc)[:500])
            return None

        self.db.mark_schedule_run(schedule_id, run_id=run.id)
        if self.settings.ai_model:
            engine = self.analysis_engine or build_engine(self.settings)
            if engine is not None:
                try:
                    await analyze_run(
                        self.db,
                        run,
                        engine,
                        timeout=self.settings.ai_timeout + 30,
                    )
                except AnalysisError as exc:
                    logger.warning("定时任务 AI 分析失败：%s", exc)
        return run
