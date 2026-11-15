"""Postgres implementation of :class:`GrowthRepository`.

Concurrency notes
-----------------
* Task and outbox claims use a single ``UPDATE ... WHERE id IN (SELECT ...
  FOR UPDATE SKIP LOCKED LIMIT n)`` statement, so two workers can never claim
  the same row.
* Rate-limit consumption runs every check inside one transaction and raises an
  internal exception as soon as one check is exhausted. That rolls back all
  earlier increments in the same call before a denied decision is returned.
* Every state transition compares the expected status in the ``WHERE`` clause;
  callers see ``False`` when another writer won the race.
* Timeline values are always bound parameters on methods that accept ``now``;
  SQL ``now()`` is only used where the method has no clock argument.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import datetime, timedelta, timezone
from typing import Any, TypeVar
from uuid import UUID

import asyncpg

from growth_core.schemas import (
    ApprovalRequest,
    GrowthSource,
    NewApprovalRequest,
    NewAuditEntry,
    NewDeliveryLog,
    NewOutboxMessage,
    NewOutreachMessage,
    NewOutreachVersion,
    NewSocialLead,
    NewTask,
    OutboxMessage,
    OutreachMessage,
    OutreachVersion,
    PipelineTask,
    PromptTemplate,
    ProviderConfig,
    RateLimitCheck,
    RateLimitDecision,
    RateLimitRule,
    ScoringRubric,
    SocialLead,
)

__all__ = ["PostgresGrowthRepository"]

_ModelT = TypeVar("_ModelT")

# JSONB columns are returned by asyncpg as text; decode them before handing a
# row to Pydantic. Only fields that actually exist on the model are listed.
_MODEL_JSON_FIELDS: dict[type, tuple[str, ...]] = {
    PipelineTask: ("payload",),
    OutboxMessage: ("payload",),
    ProviderConfig: ("config",),
    PromptTemplate: ("output_schema",),
    ScoringRubric: ("dimensions", "penalties", "thresholds"),
    GrowthSource: ("config",),
    SocialLead: ("metrics", "raw", "subreddit_rules", "score_reasons"),
    OutreachMessage: ("metadata",),
    OutreachVersion: ("risk_flags",),
    ApprovalRequest: ("payload",),
}

# Config rollback is restricted to tables with a surrogate ``id``. The column
# tuples are the complete, fixed set of identifiers allowed in a generated
# UPDATE; identifiers are never taken from caller input.
_ROLLBACK_COLUMNS: dict[str, tuple[str, ...]] = {
    "prompt_templates": (
        "key",
        "module",
        "version",
        "template",
        "user_template",
        "output_schema",
        "model_hint",
        "enabled",
    ),
    "scoring_rubrics": (
        "key",
        "version",
        "dimensions",
        "penalties",
        "thresholds",
        "enabled",
    ),
    "provider_configs": (
        "capability",
        "provider",
        "priority",
        "enabled",
        "config",
        "secret_ref",
        "config_schema_version",
        "version",
        "updated_by",
    ),
}

_ROLLBACK_JSON_COLUMNS: dict[str, frozenset[str]] = {
    "prompt_templates": frozenset({"output_schema"}),
    "scoring_rubrics": frozenset({"dimensions", "penalties", "thresholds"}),
    "provider_configs": frozenset({"config"}),
}


class _RateLimitExceeded(Exception):
    """Internal sentinel used to roll back a rate-limit transaction."""

    def __init__(self, check: RateLimitCheck, window_start: datetime) -> None:
        super().__init__(f"{check.scope}:{check.scope_key}")
        self.check = check
        self.window_start = window_start


def _now_or_default(now: datetime | None) -> datetime:
    if now is None:
        return datetime.now(timezone.utc)
    if now.tzinfo is None:
        return now.replace(tzinfo=timezone.utc)
    return now.astimezone(timezone.utc)


def _json(value: Any) -> str:
    return json.dumps(value)


def _json_or_none(value: Any) -> str | None:
    return None if value is None else json.dumps(value)


def _rowcount(status: str) -> int:
    # asyncpg returns command tags such as "UPDATE 3".
    return int(status.rsplit(" ", 1)[-1])


def _to_model(model_cls: type[_ModelT], record: asyncpg.Record | None) -> _ModelT | None:
    if record is None:
        return None
    data = dict(record)
    for field in _MODEL_JSON_FIELDS.get(model_cls, ()):
        value = data.get(field)
        if isinstance(value, str):
            data[field] = json.loads(value)
    return model_cls.model_validate(data)


def _restored_snapshot(
    record: asyncpg.Record, table_name: str
) -> dict[str, Any]:
    data = dict(record)
    for field in _ROLLBACK_JSON_COLUMNS[table_name]:
        value = data.get(field)
        if isinstance(value, str):
            data[field] = json.loads(value)
    return data


class PostgresGrowthRepository:
    """``GrowthRepository`` backed by an ``asyncpg`` pool."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    @classmethod
    async def connect(cls, database_url: str) -> "PostgresGrowthRepository":
        pool = await asyncpg.create_pool(database_url)
        return cls(pool)

    async def close(self) -> None:
        await self._pool.close()

    # ------------------------------------------------------------------
    # Configuration reads
    # ------------------------------------------------------------------
    async def list_provider_configs(
        self, tenant_id: UUID, capability: str
    ) -> list[ProviderConfig]:
        records = await self._pool.fetch(
            """
            select * from provider_configs
            where tenant_id = $1 and capability = $2 and enabled = true
            order by priority, provider
            """,
            tenant_id,
            capability,
        )
        return [_to_model(ProviderConfig, record) for record in records]

    async def get_prompt_template(
        self, tenant_id: UUID, key: str, version: int | None = None
    ) -> PromptTemplate | None:
        if version is None:
            record = await self._pool.fetchrow(
                """
                select * from prompt_templates
                where tenant_id = $1 and key = $2 and enabled = true
                order by version desc
                limit 1
                """,
                tenant_id,
                key,
            )
        else:
            record = await self._pool.fetchrow(
                """
                select * from prompt_templates
                where tenant_id = $1 and key = $2 and version = $3
                """,
                tenant_id,
                key,
                version,
            )
        return _to_model(PromptTemplate, record)

    async def get_scoring_rubric(
        self, tenant_id: UUID, key: str, version: int | None = None
    ) -> ScoringRubric | None:
        if version is None:
            record = await self._pool.fetchrow(
                """
                select * from scoring_rubrics
                where tenant_id = $1 and key = $2 and enabled = true
                order by version desc
                limit 1
                """,
                tenant_id,
                key,
            )
        else:
            record = await self._pool.fetchrow(
                """
                select * from scoring_rubrics
                where tenant_id = $1 and key = $2 and version = $3
                """,
                tenant_id,
                key,
                version,
            )
        return _to_model(ScoringRubric, record)

    async def get_feature(self, tenant_id: UUID, feature_key: str) -> bool:
        enabled = await self._pool.fetchval(
            """
            select enabled from tenant_features
            where tenant_id = $1 and feature_key = $2
            """,
            tenant_id,
            feature_key,
        )
        return bool(enabled)

    async def list_rate_limit_rules(
        self, tenant_id: UUID, channel: str
    ) -> list[RateLimitRule]:
        records = await self._pool.fetch(
            """
            select * from rate_limit_rules
            where tenant_id = $1 and channel = $2
            order by scope, scope_key
            """,
            tenant_id,
            channel,
        )
        return [_to_model(RateLimitRule, record) for record in records]

    async def ensure_tenant(self, tenant_id: UUID, workspace_id: UUID) -> None:
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "insert into tenants (id, name) values ($1, $2) "
                    "on conflict (id) do nothing",
                    tenant_id,
                    "Growth Test Tenant",
                )
                await conn.execute(
                    """
                    insert into workspaces (id, tenant_id, name)
                    values ($1, $2, $3)
                    on conflict (id) do nothing
                    """,
                    workspace_id,
                    tenant_id,
                    "Default",
                )

    async def add_source(self, source: GrowthSource) -> None:
        await self._pool.execute(
            """
            insert into growth_sources
                (id, tenant_id, workspace_id, source_type, platform,
                 dedupe_key, config, cadence_minutes, enabled, last_run_at,
                 last_error, version)
            values ($1, $2, $3, $4, $5, $6, $7::jsonb, $8, $9, $10, $11, $12)
            on conflict (tenant_id, dedupe_key) do nothing
            """,
            source.id,
            source.tenant_id,
            source.workspace_id,
            source.source_type,
            source.platform,
            source.dedupe_key,
            _json(source.config),
            source.cadence_minutes,
            source.enabled,
            source.last_run_at,
            source.last_error,
            source.version,
        )

    # ------------------------------------------------------------------
    # Pipeline tasks
    # ------------------------------------------------------------------
    async def enqueue_task(self, task: NewTask) -> UUID:
        record = await self._pool.fetchrow(
            """
            insert into pipeline_runs
                (tenant_id, workspace_id, pipeline, task_type, payload,
                 idempotency_key, priority, run_after, max_attempts, status)
            values ($1, $2, $3, $4, $5::jsonb, $6, $7,
                    coalesce($8::timestamptz, now()), $9, 'queued')
            on conflict (tenant_id, idempotency_key) do nothing
            returning *
            """,
            task.tenant_id,
            task.workspace_id,
            task.pipeline,
            task.task_type,
            _json(task.payload),
            task.idempotency_key,
            task.priority,
            task.run_after,
            task.max_attempts,
        )
        if record is None:
            record = await self._pool.fetchrow(
                """
                select id from pipeline_runs
                where tenant_id = $1 and idempotency_key = $2
                """,
                task.tenant_id,
                task.idempotency_key,
            )
        return record["id"]

    async def claim_task(
        self, worker_id: str, now: datetime | None = None
    ) -> PipelineTask | None:
        clock = _now_or_default(now)
        record = await self._pool.fetchrow(
            """
            update pipeline_runs
            set status = 'running',
                locked_at = $3::timestamptz,
                locked_by = $1,
                updated_at = $3::timestamptz
            where id = (
                select id from pipeline_runs
                where status = 'queued' and run_after <= $2::timestamptz
                order by priority, run_after, created_at
                for update skip locked
                limit 1
            )
            returning *
            """,
            worker_id,
            clock,
            clock,
        )
        return _to_model(PipelineTask, record)

    async def complete_task(self, task_id: UUID) -> None:
        await self._pool.execute(
            """
            update pipeline_runs
            set status = 'succeeded',
                locked_at = null,
                locked_by = null,
                updated_at = now()
            where id = $1
            """,
            task_id,
        )

    async def fail_task(
        self, task_id: UUID, error: str, now: datetime | None = None
    ) -> None:
        clock = _now_or_default(now)
        await self._pool.execute(
            """
            update pipeline_runs
            set attempts = attempts + 1,
                status = case when attempts + 1 >= max_attempts
                              then 'dead' else 'queued' end,
                run_after = case when attempts + 1 >= max_attempts
                                 then run_after
                                 else $2::timestamptz
                                      + (60 * power(2, attempts))
                                        * interval '1 second' end,
                last_error = $3,
                locked_at = null,
                locked_by = null,
                updated_at = $2::timestamptz
            where id = $1
            """,
            task_id,
            clock,
            error,
        )

    async def reclaim_stale_tasks(
        self, older_than_seconds: int, now: datetime | None = None
    ) -> int:
        clock = _now_or_default(now)
        status = await self._pool.execute(
            """
            update pipeline_runs
            set status = 'queued',
                locked_at = null,
                locked_by = null,
                updated_at = $2::timestamptz
            where status = 'running'
              and locked_at is not null
              and locked_at < $2::timestamptz
                              - ($1::int * interval '1 second')
            """,
            int(older_than_seconds),
            clock,
        )
        return _rowcount(status)

    # ------------------------------------------------------------------
    # Transactional outbox
    # ------------------------------------------------------------------
    async def enqueue_outbox(self, message: NewOutboxMessage) -> UUID:
        record = await self._pool.fetchrow(
            """
            insert into outbox_messages
                (tenant_id, workspace_id, topic, payload, status,
                 idempotency_key, next_attempt_at)
            values ($1, $2, $3, $4::jsonb, 'pending', $5,
                    coalesce($6::timestamptz, now()))
            on conflict (tenant_id, idempotency_key) do nothing
            returning *
            """,
            message.tenant_id,
            message.workspace_id,
            message.topic,
            _json(message.payload),
            message.idempotency_key,
            message.next_attempt_at,
        )
        if record is None:
            record = await self._pool.fetchrow(
                """
                select id from outbox_messages
                where tenant_id = $1 and idempotency_key = $2
                """,
                message.tenant_id,
                message.idempotency_key,
            )
        return record["id"]

    async def claim_outbox(
        self, limit: int = 10, now: datetime | None = None
    ) -> list[OutboxMessage]:
        clock = _now_or_default(now)
        records = await self._pool.fetch(
            """
            update outbox_messages
            set status = 'sending',
                updated_at = $2::timestamptz
            where id in (
                select id from outbox_messages
                where status in ('pending', 'failed')
                  and next_attempt_at <= $2::timestamptz
                order by next_attempt_at, created_at
                for update skip locked
                limit $1::int
            )
            returning *
            """,
            int(limit),
            clock,
        )
        return [_to_model(OutboxMessage, record) for record in records]

    async def mark_outbox_sent(self, outbox_id: UUID) -> None:
        await self._pool.execute(
            """
            update outbox_messages
            set status = 'sent',
                last_error = null,
                updated_at = now()
            where id = $1
            """,
            outbox_id,
        )

    async def mark_outbox_failed(
        self, outbox_id: UUID, error: str, now: datetime | None = None
    ) -> None:
        clock = _now_or_default(now)
        await self._pool.execute(
            """
            update outbox_messages
            set attempts = attempts + 1,
                status = case when attempts + 1 >= 5
                              then 'dead' else 'failed' end,
                next_attempt_at = case when attempts + 1 >= 5
                                       then next_attempt_at
                                       else $2::timestamptz
                                            + (60 * power(2, attempts))
                                              * interval '1 second' end,
                last_error = $3,
                updated_at = $2::timestamptz
            where id = $1
            """,
            outbox_id,
            clock,
            error,
        )

    # ------------------------------------------------------------------
    # Rate limits, suppression, audit, config rollback
    # ------------------------------------------------------------------
    async def consume_rate_limits(
        self,
        tenant_id: UUID,
        checks: Sequence[RateLimitCheck],
        now: datetime | None = None,
    ) -> RateLimitDecision:
        clock = _now_or_default(now)
        ordered_checks = list(checks)
        try:
            async with self._pool.acquire() as conn:
                async with conn.transaction():
                    for check in ordered_checks:
                        window_start = clock - timedelta(
                            seconds=int(clock.timestamp()) % check.window_seconds
                        )
                        record = await conn.fetchrow(
                            """
                            insert into rate_limit_counters
                                (tenant_id, channel, scope, scope_key,
                                 window_start, count)
                            values ($1, $2, $3, $4, $5, 1)
                            on conflict (tenant_id, channel, scope, scope_key,
                                         window_start)
                            do update set
                                count = rate_limit_counters.count + 1
                            where rate_limit_counters.count < $6
                            returning count
                            """,
                            tenant_id,
                            check.channel,
                            check.scope,
                            check.scope_key,
                            window_start,
                            check.max_count,
                        )
                        if record is None:
                            raise _RateLimitExceeded(check, window_start)
        except _RateLimitExceeded as exc:
            window_end = exc.window_start + timedelta(
                seconds=exc.check.window_seconds
            )
            retry_after = max(
                0, int((window_end - clock).total_seconds())
            )
            return RateLimitDecision(
                allowed=False,
                exceeded_scope=exc.check.scope,
                exceeded_scope_key=exc.check.scope_key,
                retry_after_seconds=retry_after,
            )
        return RateLimitDecision(allowed=True)

    async def is_suppressed(self, tenant_id: UUID, kind: str, value: str) -> bool:
        return bool(
            await self._pool.fetchval(
                """
                select exists (
                    select 1 from suppression_list
                    where tenant_id = $1 and kind = $2 and value = $3
                )
                """,
                tenant_id,
                kind,
                value,
            )
        )

    async def add_suppression(
        self,
        tenant_id: UUID,
        kind: str,
        value: str,
        reason: str,
        source: str = "",
    ) -> None:
        await self._pool.execute(
            """
            insert into suppression_list
                (tenant_id, kind, value, reason, source)
            values ($1, $2, $3, $4, $5)
            on conflict (tenant_id, kind, value) do nothing
            """,
            tenant_id,
            kind,
            value,
            reason,
            source,
        )

    async def write_audit(self, entry: NewAuditEntry) -> None:
        await self._pool.execute(
            """
            insert into audit_log
                (tenant_id, workspace_id, actor_type, actor_id, action,
                 entity_type, entity_id, before, after)
            values ($1, $2, $3, $4, $5, $6, $7, $8::jsonb, $9::jsonb)
            """,
            entry.tenant_id,
            entry.workspace_id,
            entry.actor_type,
            entry.actor_id,
            entry.action,
            entry.entity_type,
            entry.entity_id,
            _json_or_none(entry.before),
            _json_or_none(entry.after),
        )

    async def rollback_config_version(
        self, tenant_id: UUID, version_id: UUID, changed_by: str
    ) -> bool:
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                version_row = await conn.fetchrow(
                    """
                    select table_name, record_id, version, snapshot
                    from config_versions
                    where id = $1 and tenant_id = $2
                    for update
                    """,
                    version_id,
                    tenant_id,
                )
                if version_row is None:
                    return False

                table_name = version_row["table_name"]
                if table_name not in _ROLLBACK_COLUMNS:
                    raise ValueError(
                        f"Unsupported table for config rollback: {table_name}"
                    )

                snapshot = version_row["snapshot"]
                if isinstance(snapshot, str):
                    snapshot = json.loads(snapshot)
                if not isinstance(snapshot, dict):
                    raise ValueError("config_versions snapshot is not an object")

                record_id = version_row["record_id"]
                columns = _ROLLBACK_COLUMNS[table_name]
                json_columns = _ROLLBACK_JSON_COLUMNS[table_name]

                assignments: list[str] = []
                params: list[Any] = [tenant_id, record_id]
                for column in columns:
                    placeholder = f"${len(params) + 1}"
                    if column in json_columns:
                        assignments.append(f"{column} = {placeholder}::jsonb")
                        params.append(_json(snapshot.get(column)))
                    else:
                        assignments.append(f"{column} = {placeholder}")
                        params.append(snapshot.get(column))

                if table_name == "provider_configs":
                    assignments.append("updated_at = now()")

                # ``table_name`` is a validated key from the fixed dict and
                # every identifier in ``assignments`` comes from the fixed
                # column tuples above, never from caller-controlled data.
                restored = await conn.fetchrow(
                    f"update {table_name} set {', '.join(assignments)} "
                    "where tenant_id = $1 and id = $2 returning *",
                    *params,
                )
                if restored is None:
                    return False

                await conn.execute(
                    """
                    insert into config_versions
                        (tenant_id, table_name, record_id, version, diff,
                         snapshot, changed_by)
                    values ($1, $2, $3, $4, $5::jsonb, $6::jsonb, $7)
                    """,
                    tenant_id,
                    table_name,
                    record_id,
                    int(version_row["version"]) + 1,
                    _json(
                        {
                            "rolled_back_from": str(version_id),
                            "restored": True,
                        }
                    ),
                    json.dumps(
                        _restored_snapshot(restored, table_name), default=str
                    ),
                    changed_by,
                )
                return True

    # ------------------------------------------------------------------
    # Sources and leads
    # ------------------------------------------------------------------
    async def list_enabled_sources(self, tenant_id: UUID) -> list[GrowthSource]:
        records = await self._pool.fetch(
            """
            select * from growth_sources
            where tenant_id = $1 and enabled = true
            order by source_type, platform, id
            """,
            tenant_id,
        )
        return [_to_model(GrowthSource, record) for record in records]

    async def update_source_run(
        self,
        tenant_id: UUID,
        source_id: UUID,
        last_run_at: datetime,
        last_error: str | None = None,
    ) -> None:
        await self._pool.execute(
            """
            update growth_sources
            set last_run_at = $3,
                last_error = $4,
                updated_at = now()
            where tenant_id = $1 and id = $2
            """,
            tenant_id,
            source_id,
            last_run_at,
            last_error,
        )

    async def upsert_lead(self, lead: NewSocialLead) -> tuple[SocialLead, bool]:
        record = await self._pool.fetchrow(
            """
            insert into social_leads
                (tenant_id, workspace_id, source_id, platform,
                 platform_post_id, title, body, author_public, source_url,
                 published_at, metrics, raw, subreddit, subreddit_rules,
                 dedupe_key, status)
            values ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11::jsonb,
                    $12::jsonb, $13, $14::jsonb, $15, 'discovered')
            on conflict (tenant_id, dedupe_key) do nothing
            returning *
            """,
            lead.tenant_id,
            lead.workspace_id,
            lead.source_id,
            lead.platform,
            lead.platform_post_id,
            lead.title,
            lead.body,
            lead.author_public,
            lead.source_url,
            lead.published_at,
            _json(lead.metrics),
            _json_or_none(lead.raw),
            lead.subreddit,
            _json(lead.subreddit_rules),
            lead.dedupe_key,
        )
        if record is not None:
            return _to_model(SocialLead, record), True

        record = await self._pool.fetchrow(
            """
            select * from social_leads
            where tenant_id = $1 and dedupe_key = $2
            """,
            lead.tenant_id,
            lead.dedupe_key,
        )
        return _to_model(SocialLead, record), False

    async def get_lead(
        self, tenant_id: UUID, lead_id: UUID
    ) -> SocialLead | None:
        record = await self._pool.fetchrow(
            "select * from social_leads where tenant_id = $1 and id = $2",
            tenant_id,
            lead_id,
        )
        return _to_model(SocialLead, record)

    async def list_leads(
        self, tenant_id: UUID, status: str | None = None, limit: int = 50
    ) -> list[SocialLead]:
        records = await self._pool.fetch(
            """
            select * from social_leads
            where tenant_id = $1
              and ($2::text is null or status = $2::text)
            order by created_at desc, id
            limit $3::int
            """,
            tenant_id,
            status,
            int(limit),
        )
        return [_to_model(SocialLead, record) for record in records]

    async def update_lead_status(
        self,
        tenant_id: UUID,
        lead_id: UUID,
        expected_status: str,
        status: str,
        *,
        score: int | None = None,
        score_reasons: dict[str, Any] | None = None,
        model: str | None = None,
        prompt_version: str | None = None,
    ) -> bool:
        status_tag = await self._pool.execute(
            """
            update social_leads
            set status = $4,
                score = coalesce($5::int, score),
                score_reasons = coalesce($6::jsonb, score_reasons),
                model = coalesce($7, model),
                prompt_version = coalesce($8, prompt_version),
                version = version + 1,
                updated_at = now()
            where tenant_id = $1 and id = $2 and status = $3
            """,
            tenant_id,
            lead_id,
            expected_status,
            status,
            score,
            _json_or_none(score_reasons),
            model,
            prompt_version,
        )
        return _rowcount(status_tag) == 1

    # ------------------------------------------------------------------
    # Outreach messages and versions
    # ------------------------------------------------------------------
    async def create_message(self, message: NewOutreachMessage) -> OutreachMessage:
        record = await self._pool.fetchrow(
            """
            insert into outreach_messages
                (tenant_id, workspace_id, channel, provider, lead_id, user_id,
                 rule_key, status, scheduled_at, dedupe_key, metadata)
            values ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11::jsonb)
            on conflict (tenant_id, dedupe_key) do nothing
            returning *
            """,
            message.tenant_id,
            message.workspace_id,
            message.channel,
            message.provider,
            message.lead_id,
            message.user_id,
            message.rule_key,
            message.status,
            message.scheduled_at,
            message.dedupe_key,
            _json(message.metadata),
        )
        if record is None:
            record = await self._pool.fetchrow(
                """
                select * from outreach_messages
                where tenant_id = $1 and dedupe_key = $2
                """,
                message.tenant_id,
                message.dedupe_key,
            )
        return _to_model(OutreachMessage, record)

    async def get_message(
        self, tenant_id: UUID, message_id: UUID
    ) -> OutreachMessage | None:
        record = await self._pool.fetchrow(
            "select * from outreach_messages where tenant_id = $1 and id = $2",
            tenant_id,
            message_id,
        )
        return _to_model(OutreachMessage, record)

    async def list_messages(
        self, tenant_id: UUID, status: str | None = None, limit: int = 50
    ) -> list[OutreachMessage]:
        records = await self._pool.fetch(
            """
            select * from outreach_messages
            where tenant_id = $1
              and ($2::text is null or status = $2::text)
            order by created_at desc, id
            limit $3::int
            """,
            tenant_id,
            status,
            int(limit),
        )
        return [_to_model(OutreachMessage, record) for record in records]

    async def find_message_by_dedupe_key(
        self, tenant_id: UUID, dedupe_key: str
    ) -> OutreachMessage | None:
        record = await self._pool.fetchrow(
            """
            select * from outreach_messages
            where tenant_id = $1 and dedupe_key = $2
            """,
            tenant_id,
            dedupe_key,
        )
        return _to_model(OutreachMessage, record)

    async def update_message_status(
        self,
        tenant_id: UUID,
        message_id: UUID,
        expected_status: str,
        status: str,
        *,
        sent_at: datetime | None = None,
        provider: str | None = None,
        provider_message_id: str | None = None,
        metadata_patch: dict[str, Any] | None = None,
    ) -> bool:
        status_tag = await self._pool.execute(
            """
            update outreach_messages
            set status = $4,
                sent_at = coalesce($5::timestamptz, sent_at),
                provider = coalesce($6, provider),
                provider_message_id = coalesce($7, provider_message_id),
                metadata = case
                    when $8::jsonb is null then metadata
                    else metadata || $8::jsonb
                end,
                version = version + 1,
                updated_at = now()
            where tenant_id = $1 and id = $2 and status = $3
            """,
            tenant_id,
            message_id,
            expected_status,
            status,
            sent_at,
            provider,
            provider_message_id,
            _json_or_none(metadata_patch),
        )
        return _rowcount(status_tag) == 1

    async def create_version(self, version: NewOutreachVersion) -> OutreachVersion:
        record = await self._pool.fetchrow(
            """
            insert into outreach_versions
                (tenant_id, message_id, version, body_text, subject, cta_url,
                 model, prompt_version, risk_flags)
            values ($1, $2, $3, $4, $5, $6, $7, $8, $9::jsonb)
            returning *
            """,
            version.tenant_id,
            version.message_id,
            version.version,
            version.body_text,
            version.subject,
            version.cta_url,
            version.model,
            version.prompt_version,
            _json(version.risk_flags),
        )
        return _to_model(OutreachVersion, record)

    async def get_latest_version(
        self, tenant_id: UUID, message_id: UUID
    ) -> OutreachVersion | None:
        record = await self._pool.fetchrow(
            """
            select * from outreach_versions
            where tenant_id = $1 and message_id = $2
            order by version desc
            limit 1
            """,
            tenant_id,
            message_id,
        )
        return _to_model(OutreachVersion, record)

    async def mark_version_approved(
        self,
        tenant_id: UUID,
        version_id: UUID,
        approved_by: str,
        approved_at: datetime,
    ) -> None:
        await self._pool.execute(
            """
            update outreach_versions
            set approved_by = $3, approved_at = $4
            where tenant_id = $1 and id = $2
            """,
            tenant_id,
            version_id,
            approved_by,
            approved_at,
        )

    async def record_delivery(self, entry: NewDeliveryLog) -> None:
        await self._pool.execute(
            """
            insert into delivery_log
                (tenant_id, workspace_id, message_id, lead_id, provider,
                 event_type, payload)
            values ($1, $2, $3, $4, $5, $6, $7::jsonb)
            """,
            entry.tenant_id,
            entry.workspace_id,
            entry.message_id,
            entry.lead_id,
            entry.provider,
            entry.event_type,
            _json(entry.payload),
        )

    async def count_followups(
        self, tenant_id: UUID, original_message_id: UUID
    ) -> int:
        return int(
            await self._pool.fetchval(
                """
                select count(*) from outreach_messages
                where tenant_id = $1
                  and metadata->>'followup_of' = $2
                """,
                tenant_id,
                str(original_message_id),
            )
        )

    async def latest_sent_at(
        self, tenant_id: UUID, lead_id: UUID
    ) -> datetime | None:
        return await self._pool.fetchval(
            """
            select max(sent_at) from outreach_messages
            where tenant_id = $1 and lead_id = $2 and sent_at is not null
            """,
            tenant_id,
            lead_id,
        )

    # ------------------------------------------------------------------
    # Approval requests
    # ------------------------------------------------------------------
    async def create_approval_request(
        self, request: NewApprovalRequest
    ) -> ApprovalRequest:
        record = await self._pool.fetchrow(
            """
            insert into approval_requests
                (tenant_id, workspace_id, message_id, approval_id, provider,
                 external_id, payload, status)
            values ($1, $2, $3, $4, $5, $6, $7::jsonb, 'pending')
            on conflict (tenant_id, approval_id) do nothing
            returning *
            """,
            request.tenant_id,
            request.workspace_id,
            request.message_id,
            request.approval_id,
            request.provider,
            request.external_id,
            _json(request.payload),
        )
        if record is None:
            record = await self._pool.fetchrow(
                """
                select * from approval_requests
                where tenant_id = $1 and approval_id = $2
                """,
                request.tenant_id,
                request.approval_id,
            )
        return _to_model(ApprovalRequest, record)

    async def get_approval_request(
        self, tenant_id: UUID, approval_id: str
    ) -> ApprovalRequest | None:
        record = await self._pool.fetchrow(
            """
            select * from approval_requests
            where tenant_id = $1 and approval_id = $2
            """,
            tenant_id,
            approval_id,
        )
        return _to_model(ApprovalRequest, record)

    async def decide_approval(
        self,
        tenant_id: UUID,
        approval_id: str,
        status: str,
        decided_by: str,
        reason: str = "",
    ) -> bool:
        status_tag = await self._pool.execute(
            """
            update approval_requests
            set status = $3,
                decided_by = $4,
                decided_at = now(),
                reason = $5,
                version = version + 1,
                updated_at = now()
            where tenant_id = $1 and approval_id = $2 and status = 'pending'
            """,
            tenant_id,
            approval_id,
            status,
            decided_by,
            reason,
        )
        return _rowcount(status_tag) == 1

    async def expire_pending_approvals(
        self, tenant_id: UUID, message_id: UUID
    ) -> int:
        status_tag = await self._pool.execute(
            """
            update approval_requests
            set status = 'expired',
                decided_at = now(),
                version = version + 1,
                updated_at = now()
            where tenant_id = $1 and message_id = $2 and status = 'pending'
            """,
            tenant_id,
            message_id,
        )
        return _rowcount(status_tag)

    async def set_approval_external_id(
        self, tenant_id: UUID, approval_id: str, external_id: str
    ) -> None:
        await self._pool.execute(
            """
            update approval_requests
            set external_id = $3, updated_at = now()
            where tenant_id = $1 and approval_id = $2
            """,
            tenant_id,
            approval_id,
            external_id,
        )

    # ------------------------------------------------------------------
    # Test-only helpers
    # ------------------------------------------------------------------
    async def truncate_all_for_tests(self) -> None:
        """Remove all Growth data. Test-only; never expose through the API."""
        await self._pool.execute("truncate tenants cascade")
