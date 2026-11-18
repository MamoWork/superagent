"""Social ingestion: fetch source posts, dedupe leads, and enqueue scoring.

The service runs every enabled source independently. A failing source (an
adapter error, an unexpected exception, or a missing adapter) never aborts the
run: the failure is recorded as a :class:`SourceError` and the loop continues
with the next source.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import UUID

from growth_core.adapters.base import AdapterError, RawPost, SourceAdapter
from growth_core.repositories.base import GrowthRepository
from growth_core.schemas import GrowthSource, NewSocialLead, NewTask

__all__ = ["IngestResult", "SourceError", "ingest_social"]

_MISSING_ADAPTER = "ADAPTER_NOT_CONFIGURED"
_UNEXPECTED = "UNEXPECTED_ERROR"


@dataclass(frozen=True)
class SourceError:
    """A source-level failure captured during an ingestion run."""

    source_id: UUID
    code: str
    message: str


@dataclass
class IngestResult:
    """Per-run counters plus every source failure encountered."""

    created: int
    duplicates: int
    errors: list[SourceError] = field(default_factory=list)


def _dedupe_key(post: RawPost) -> str:
    """Stable digest of the platform post identity."""
    return hashlib.sha256(
        f"{post.platform}:{post.platform_post_id}".encode("utf-8")
    ).hexdigest()


def _subreddit_rules(source: GrowthSource) -> dict:
    rules = source.config.get("subreddit_rules")
    return rules if isinstance(rules, dict) else {}


def _new_lead(
    post: RawPost,
    source: GrowthSource,
    tenant_id: UUID,
    workspace_id: UUID,
) -> NewSocialLead:
    return NewSocialLead(
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        source_id=source.id,
        platform=post.platform,
        platform_post_id=post.platform_post_id,
        title=post.title,
        body=post.body,
        author_public=post.author_public,
        source_url=post.source_url,
        published_at=post.published_at,
        metrics=post.metrics,
        raw=post.raw,
        subreddit=post.subreddit,
        subreddit_rules=_subreddit_rules(source),
        dedupe_key=_dedupe_key(post),
    )


def _score_task(
    lead_id: UUID, tenant_id: UUID, workspace_id: UUID
) -> NewTask:
    return NewTask(
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        pipeline="social",
        task_type="social.score",
        payload={"lead_id": str(lead_id)},
        idempotency_key=f"score:{lead_id}",
    )


async def _record_error(
    repo: GrowthRepository,
    tenant_id: UUID,
    source_id: UUID,
    code: str,
    message: str,
    now: datetime,
    errors: list[SourceError],
) -> None:
    errors.append(SourceError(source_id, code, message))
    await repo.update_source_run(
        tenant_id,
        source_id,
        last_run_at=now,
        last_error=f"{code}: {message}",
    )


async def ingest_social(
    repo: GrowthRepository,
    adapters: Mapping[str, SourceAdapter],
    *,
    tenant_id: UUID,
    workspace_id: UUID,
    now: datetime | None = None,
) -> IngestResult:
    """Fetch all enabled sources for ``tenant_id`` and persist new leads.

    ``now`` is the run clock: every source processed in this call shares the
    same value for ``last_run_at``. Each source's posts are deduplicated via a
    ``sha256(platform:platform_post_id)`` key, and newly created leads get a
    ``social.score`` pipeline task.
    """
    clock = now if now is not None else datetime.now(timezone.utc)
    result = IngestResult(created=0, duplicates=0)

    for source in await repo.list_enabled_sources(tenant_id):
        try:
            adapter = adapters.get(source.source_type)
            if adapter is None:
                message = f"no adapter for source_type {source.source_type}"
                await _record_error(
                    repo,
                    tenant_id,
                    source.id,
                    _MISSING_ADAPTER,
                    message,
                    clock,
                    result.errors,
                )
                continue

            posts = await adapter.fetch(source)
            for post in posts:
                lead, created = await repo.upsert_lead(
                    _new_lead(post, source, tenant_id, workspace_id)
                )
                if created:
                    result.created += 1
                    await repo.enqueue_task(
                        _score_task(lead.id, tenant_id, workspace_id)
                    )
                else:
                    result.duplicates += 1
        except AdapterError as exc:
            await _record_error(
                repo,
                tenant_id,
                source.id,
                type(exc).__name__,
                str(exc),
                clock,
                result.errors,
            )
        except Exception as exc:  # noqa: BLE001 - one source must not abort the run
            await _record_error(
                repo,
                tenant_id,
                source.id,
                _UNEXPECTED,
                f"{type(exc).__name__}: {exc}",
                clock,
                result.errors,
            )
        else:
            await repo.update_source_run(
                tenant_id,
                source.id,
                last_run_at=clock,
                last_error=None,
            )

    return result
