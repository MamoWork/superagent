from __future__ import annotations

import asyncio
import uuid
from typing import Any

from app.db import Database, utcnow
from app.domain_packs import get_pack
from app.providers.base import ProviderError
from app.providers.registry import ProviderRegistry
from app.schemas import (
    ProviderErrorInfo,
    Run,
    RunCreate,
    SearchQuery,
    Signal,
)


def build_query_text(payload: RunCreate) -> str:
    parts = [payload.direction.strip()]
    lower_direction = payload.direction.lower()
    for keyword in payload.keywords:
        keyword = keyword.strip()
        if keyword and keyword.lower() not in lower_direction:
            parts.append(keyword)
    return " ".join(parts)[:500]


def _error_info(exc: BaseException) -> ProviderErrorInfo:
    if isinstance(exc, ProviderError):
        return ProviderErrorInfo(
            code=exc.code,
            message=exc.message,
            hint=exc.hint,
            retry_after_seconds=exc.retry_after_seconds,
        )
    if isinstance(exc, asyncio.TimeoutError):
        return ProviderErrorInfo(
            code="PROVIDER_TIMEOUT",
            message="数据源调用超时。",
            hint="稍后重试；不要循环重试或切换账号。",
        )
    return ProviderErrorInfo(
        code="PROVIDER_ERROR",
        message=str(exc) or exc.__class__.__name__,
    )


def get_run_detail(db: Database, run_id: str) -> Run | None:
    data = db.get_run(run_id)
    if not data:
        return None
    return Run(
        **data,
        signals=db.get_signals(run_id),
        has_analysis=db.has_analysis(run_id),
    )


async def execute_run(
    db: Database,
    registry: ProviderRegistry,
    payload: RunCreate,
) -> Run:
    unknown = [pid for pid in payload.provider_ids if pid not in registry.ids()]
    if unknown:
        raise ValueError(f"未知数据源：{', '.join(unknown)}")
    try:
        pack = get_pack(payload.domain_pack)
    except KeyError as exc:
        raise ValueError(str(exc)) from exc

    run_id = f"run_{uuid.uuid4().hex[:12]}"
    query_text = build_query_text(payload)
    provider_ids = list(dict.fromkeys(payload.provider_ids))
    db.create_run(
        {
            "id": run_id,
            "workspace_id": payload.workspace_id,
            "domain_pack": payload.domain_pack,
            "direction": payload.direction,
            "keywords": payload.keywords,
            "provider_ids": provider_ids,
            "status": "running",
            "stats": {},
            "created_at": utcnow(),
        }
    )

    query = SearchQuery(
        text=query_text,
        keywords=payload.keywords,
        limit=payload.limit_per_provider,
        time_range_days=payload.time_range_days,
        domain_pack=payload.domain_pack,
    )

    providers = [registry.get(pid) for pid in provider_ids]
    results = await asyncio.gather(
        *(provider.search(query) for provider in providers),
        return_exceptions=True,
    )

    all_signals: list[Signal] = []
    provider_counts: dict[str, int] = {}
    provider_errors: dict[str, ProviderErrorInfo] = {}

    for provider_id, result in zip(provider_ids, results):
        if isinstance(result, BaseException):
            provider_counts[provider_id] = 0
            provider_errors[provider_id] = _error_info(result)
            continue
        provider_counts[provider_id] = len(result)
        all_signals.extend(result)

    deduped: dict[str, Signal] = {}
    for signal in all_signals:
        deduped[signal.id] = signal
    all_signals = list(deduped.values())
    db.add_signals(run_id, all_signals)

    if provider_errors and len(provider_errors) == len(provider_ids):
        status = "failed"
    elif provider_errors:
        status = "partial"
    else:
        status = "completed"

    stats: dict[str, Any] = {
        "signal_count": len(all_signals),
        "domain_pack_name": pack.name,
        "time_range_days": payload.time_range_days,
        "limit_per_provider": payload.limit_per_provider,
        "provider_counts": provider_counts,
        "provider_errors": {
            key: value.model_dump() for key, value in provider_errors.items()
        },
        "query": query_text,
    }
    db.update_run(
        run_id,
        status=status,
        stats=stats,
        finished_at=utcnow(),
    )

    detail = get_run_detail(db, run_id)
    assert detail is not None
    return detail
