"""In-memory :class:`GrowthRepository` for deterministic, DB-free tests.

Every method mirrors the semantics of :class:`PostgresGrowthRepository`:

* tasks and outbox rows are idempotent per ``(tenant_id, idempotency_key)``;
* terminal task/outbox writes are compare-and-set and honor the worker fence;
* rate-limit consumption is all-or-nothing, keyed by
  ``(tenant_id, channel, scope, scope_key, window_start)``;
* terminal message/lead/approval writes are compare-and-set on the expected
  status.

The stored rows are exposed as public attributes so tests can seed fixtures
with the Pydantic models directly (or inspect state after a call).
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID, uuid4

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

__all__ = ["FakeGrowthRepository", "FakeNotifier"]

_OUTBOX_MAX_ATTEMPTS = 5

# Same whitelist as the Postgres implementation: config rollback only works for
# tables that have a surrogate ``id`` column.
_ROLLBACK_FIELDS: dict[str, tuple[str, ...]] = {
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


def _aware(value: datetime | None) -> datetime | None:
    """Normalize a datetime to aware UTC, matching the Postgres repository."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _now_or_default(now: datetime | None) -> datetime:
    if now is None:
        return datetime.now(timezone.utc)
    aware = _aware(now)
    assert aware is not None
    return aware


def _window_start(now: datetime, window_seconds: int) -> datetime:
    """Floor ``now`` by the epoch modulo, exactly as Postgres does."""
    return now - timedelta(seconds=int(now.timestamp()) % window_seconds)


def _retry_after(now: datetime, window_start: datetime, window_seconds: int) -> int:
    window_end = window_start + timedelta(seconds=window_seconds)
    return max(0, int((window_end - now).total_seconds()))


def _same_uuid(left: Any, right: Any) -> bool:
    return left is not None and right is not None and str(left) == str(right)


def _feature_enabled(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, dict):
        return bool(value.get("enabled"))
    return bool(getattr(value, "enabled", value))


#: Mirrors the ``suppression_list.reason`` CHECK in ``0002_social.sql`` so unit
#: tests catch invalid reasons that Postgres would reject.
_ALLOWED_SUPPRESSION_REASONS = frozenset(
    {
        "unsubscribe",
        "hard_bounce",
        "complaint",
        "manual",
        "negative_reply",
        "moderator_warning",
    }
)


class FakeGrowthRepository:
    """``GrowthRepository`` backed by dicts and lists."""

    def __init__(self) -> None:
        # Rows exposed to tests -----------------------------------------
        self.tasks: list[PipelineTask] = []
        self.outbox: list[OutboxMessage] = []
        self.leads: list[SocialLead] = []
        self.messages: list[OutreachMessage] = []
        self.sources: list[GrowthSource] = []
        self.approvals: list[ApprovalRequest] = []
        self.outreach_versions: list[OutreachVersion] = []
        self.deliveries: list[dict[str, Any]] = []
        self.audit: list[dict[str, Any]] = []
        self.suppressions: dict[tuple[UUID, str, str], tuple[str, str]] = {}

        # Configuration rows keyed for direct seeding -------------------
        self.prompts: dict[tuple[UUID, str, int], PromptTemplate] = {}
        self.rubrics: dict[tuple[UUID, str, int], ScoringRubric] = {}
        self.provider_configs: dict[tuple[UUID, str, str], ProviderConfig] = {}
        self.rate_rules: dict[tuple[UUID, str, str, str], RateLimitRule] = {}
        self.features: dict[tuple[UUID, str], Any] = {}
        self.versions: dict[UUID, dict[str, Any]] = {}
        self.counters: dict[tuple[UUID, str, str, str, datetime], int] = {}

    # ------------------------------------------------------------------
    # Configuration reads
    # ------------------------------------------------------------------
    async def list_provider_configs(
        self, tenant_id: UUID, capability: str
    ) -> list[ProviderConfig]:
        rows = [
            config
            for config in self.provider_configs.values()
            if config.tenant_id == tenant_id
            and config.capability == capability
            and config.enabled
        ]
        return [
            config.model_copy(deep=True)
            for config in sorted(
                rows, key=lambda config: (config.priority, config.provider)
            )
        ]

    async def get_prompt_template(
        self, tenant_id: UUID, key: str, version: int | None = None
    ) -> PromptTemplate | None:
        matches = [
            prompt
            for prompt in self.prompts.values()
            if prompt.tenant_id == tenant_id and prompt.key == key
        ]
        if version is None:
            matches = [prompt for prompt in matches if prompt.enabled]
            if not matches:
                return None
            return max(
                matches, key=lambda prompt: prompt.version
            ).model_copy(deep=True)
        for prompt in matches:
            if prompt.version == version:
                return prompt.model_copy(deep=True)
        return None

    async def get_scoring_rubric(
        self, tenant_id: UUID, key: str, version: int | None = None
    ) -> ScoringRubric | None:
        matches = [
            rubric
            for rubric in self.rubrics.values()
            if rubric.tenant_id == tenant_id and rubric.key == key
        ]
        if version is None:
            matches = [rubric for rubric in matches if rubric.enabled]
            if not matches:
                return None
            return max(
                matches, key=lambda rubric: rubric.version
            ).model_copy(deep=True)
        for rubric in matches:
            if rubric.version == version:
                return rubric.model_copy(deep=True)
        return None

    async def get_feature(self, tenant_id: UUID, feature_key: str) -> bool:
        return _feature_enabled(self.features.get((tenant_id, feature_key)))

    async def list_rate_limit_rules(
        self, tenant_id: UUID, channel: str
    ) -> list[RateLimitRule]:
        rows = [
            rule
            for rule in self.rate_rules.values()
            if rule.tenant_id == tenant_id and rule.channel == channel
        ]
        return [
            rule.model_copy(deep=True)
            for rule in sorted(rows, key=lambda rule: (rule.scope, rule.scope_key))
        ]

    async def ensure_tenant(self, tenant_id: UUID, workspace_id: UUID) -> None:
        return None

    async def add_source(self, source: GrowthSource) -> None:
        exists = any(
            existing.tenant_id == source.tenant_id
            and existing.dedupe_key == source.dedupe_key
            for existing in self.sources
        )
        if not exists:
            self.sources.append(
                source.model_copy(
                    deep=True,
                    update={"last_run_at": _aware(source.last_run_at)},
                )
            )

    async def close(self) -> None:
        return None

    # ------------------------------------------------------------------
    # Pipeline tasks
    # ------------------------------------------------------------------
    async def enqueue_task(self, task: NewTask) -> UUID:
        for existing in self.tasks:
            if (
                existing.tenant_id == task.tenant_id
                and existing.idempotency_key == task.idempotency_key
            ):
                return existing.id

        clock = datetime.now(timezone.utc)
        data = task.model_dump()
        data["run_after"] = _aware(task.run_after) or clock
        data.update(
            id=uuid4(),
            status="queued",
            locked_at=None,
            locked_by=None,
            attempts=0,
            last_error=None,
            created_at=clock,
            updated_at=clock,
        )
        row = PipelineTask(**data)
        self.tasks.append(row.model_copy(deep=True))
        return row.id

    async def claim_task(
        self, worker_id: str, now: datetime | None = None
    ) -> PipelineTask | None:
        clock = _now_or_default(now)
        candidates = [
            task
            for task in self.tasks
            if task.status == "queued" and _aware(task.run_after) <= clock
        ]
        if not candidates:
            return None
        task = min(
            candidates,
            key=lambda item: (
                item.priority,
                _aware(item.run_after),
                _aware(item.created_at),
            ),
        )
        task.status = "running"
        task.locked_at = clock
        task.locked_by = worker_id
        task.updated_at = clock
        return task.model_copy(deep=True)

    async def complete_task(
        self, task_id: UUID, worker_id: str | None = None
    ) -> None:
        task = self._find_task(task_id)
        if task is None or task.status != "running":
            return
        if worker_id is not None and task.locked_by != worker_id:
            return
        task.status = "succeeded"
        task.locked_at = None
        task.locked_by = None
        task.updated_at = datetime.now(timezone.utc)

    async def fail_task(
        self,
        task_id: UUID,
        error: str,
        now: datetime | None = None,
        worker_id: str | None = None,
    ) -> None:
        task = self._find_task(task_id)
        if task is None or task.status != "running":
            return
        if worker_id is not None and task.locked_by != worker_id:
            return

        clock = _now_or_default(now)
        old_attempts = task.attempts
        task.attempts = old_attempts + 1
        if task.attempts >= task.max_attempts:
            task.status = "dead"
        else:
            task.status = "queued"
            task.run_after = clock + timedelta(seconds=60 * 2**old_attempts)
        task.last_error = error
        task.locked_at = None
        task.locked_by = None
        task.updated_at = clock

    async def reclaim_stale_tasks(
        self, older_than_seconds: int, now: datetime | None = None
    ) -> int:
        clock = _now_or_default(now)
        cutoff = clock - timedelta(seconds=int(older_than_seconds))
        reclaimed = 0
        for task in self.tasks:
            locked_at = _aware(task.locked_at)
            if task.status != "running" or locked_at is None or locked_at >= cutoff:
                continue
            reclaimed += 1
            task.attempts += 1
            task.status = "dead" if task.attempts >= task.max_attempts else "queued"
            task.locked_at = None
            task.locked_by = None
            task.updated_at = clock
        return reclaimed

    # ------------------------------------------------------------------
    # Transactional outbox
    # ------------------------------------------------------------------
    async def enqueue_outbox(self, message: NewOutboxMessage) -> UUID:
        for existing in self.outbox:
            if (
                existing.tenant_id == message.tenant_id
                and existing.idempotency_key == message.idempotency_key
            ):
                return existing.id

        clock = datetime.now(timezone.utc)
        data = message.model_dump()
        data["next_attempt_at"] = _aware(message.next_attempt_at) or clock
        data.update(
            id=uuid4(),
            status="pending",
            attempts=0,
            last_error=None,
            created_at=clock,
            updated_at=clock,
        )
        row = OutboxMessage(**data)
        self.outbox.append(row.model_copy(deep=True))
        return row.id

    async def claim_outbox(
        self, limit: int = 10, now: datetime | None = None
    ) -> list[OutboxMessage]:
        clock = _now_or_default(now)
        candidates = [
            row
            for row in self.outbox
            if row.status in ("pending", "failed")
            and _aware(row.next_attempt_at) <= clock
        ]
        candidates.sort(
            key=lambda row: (_aware(row.next_attempt_at), _aware(row.created_at))
        )
        claimed = candidates[: int(limit)]
        for row in claimed:
            row.status = "sending"
            row.updated_at = clock
        return [row.model_copy(deep=True) for row in claimed]

    async def mark_outbox_sent(self, outbox_id: UUID) -> None:
        row = self._find_outbox(outbox_id)
        if row is None or row.status != "sending":
            return
        row.status = "sent"
        row.last_error = None
        row.updated_at = datetime.now(timezone.utc)

    async def mark_outbox_failed(
        self, outbox_id: UUID, error: str, now: datetime | None = None
    ) -> None:
        row = self._find_outbox(outbox_id)
        if row is None or row.status != "sending":
            return

        clock = _now_or_default(now)
        old_attempts = row.attempts
        row.attempts = old_attempts + 1
        if row.attempts >= _OUTBOX_MAX_ATTEMPTS:
            row.status = "dead"
        else:
            row.status = "failed"
            row.next_attempt_at = clock + timedelta(seconds=60 * 2**old_attempts)
        row.last_error = error
        row.updated_at = clock

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

        # A non-positive limit blocks every send before any counter is
        # touched. Mirror Postgres by scanning these first.
        for check in ordered_checks:
            if check.max_count <= 0:
                window_start = _window_start(clock, check.window_seconds)
                return RateLimitDecision(
                    allowed=False,
                    exceeded_scope=check.scope,
                    exceeded_scope_key=check.scope_key,
                    retry_after_seconds=_retry_after(
                        clock, window_start, check.window_seconds
                    ),
                )

        pending: dict[tuple[UUID, str, str, str, datetime], int] = {}
        for check in ordered_checks:
            key = (
                tenant_id,
                check.channel,
                check.scope,
                check.scope_key,
                _window_start(clock, check.window_seconds),
            )
            current = self.counters.get(key, 0) + pending.get(key, 0)
            if current + 1 > check.max_count:
                window_start = key[-1]
                return RateLimitDecision(
                    allowed=False,
                    exceeded_scope=check.scope,
                    exceeded_scope_key=check.scope_key,
                    retry_after_seconds=_retry_after(
                        clock, window_start, check.window_seconds
                    ),
                )
            pending[key] = pending.get(key, 0) + 1

        for key, increment in pending.items():
            self.counters[key] = self.counters.get(key, 0) + increment
        return RateLimitDecision(allowed=True)

    async def is_suppressed(self, tenant_id: UUID, kind: str, value: str) -> bool:
        return (tenant_id, kind, value) in self.suppressions

    async def add_suppression(
        self,
        tenant_id: UUID,
        kind: str,
        value: str,
        reason: str,
        source: str = "",
    ) -> None:
        if reason not in _ALLOWED_SUPPRESSION_REASONS:
            raise ValueError(f"invalid suppression reason: {reason}")
        self.suppressions.setdefault((tenant_id, kind, value), (reason, source))

    async def write_audit(self, entry: NewAuditEntry) -> None:
        self.audit.append(
            {
                "id": uuid4(),
                "created_at": datetime.now(timezone.utc),
                **entry.model_dump(),
            }
        )

    async def rollback_config_version(
        self, tenant_id: UUID, version_id: UUID, changed_by: str
    ) -> bool:
        version_row = self.versions.get(version_id)
        if version_row is None:
            return False
        if not _same_uuid(version_row.get("tenant_id"), tenant_id):
            return False

        table_name = version_row.get("table_name")
        if table_name not in _ROLLBACK_FIELDS:
            raise ValueError(
                f"Unsupported table for config rollback: {table_name}"
            )

        snapshot = version_row.get("snapshot")
        if isinstance(snapshot, str):
            snapshot = json.loads(snapshot)
        if not isinstance(snapshot, dict):
            raise ValueError("config_versions snapshot is not an object")

        record_id = version_row.get("record_id")
        restored = self._restore_config(table_name, tenant_id, record_id, snapshot)
        if restored is None:
            return False

        new_id = uuid4()
        self.versions[new_id] = {
            "id": new_id,
            "tenant_id": tenant_id,
            "table_name": table_name,
            "record_id": record_id,
            "version": int(version_row.get("version", 0)) + 1,
            "diff": {
                "rolled_back_from": str(version_id),
                "restored": True,
            },
            "snapshot": restored.model_dump(mode="json"),
            "changed_by": changed_by,
            "created_at": datetime.now(timezone.utc),
        }
        return True

    def _restore_config(
        self,
        table_name: str,
        tenant_id: UUID,
        record_id: Any,
        snapshot: dict[str, Any],
    ) -> Any:
        if table_name == "prompt_templates":
            return self._restore_prompt(tenant_id, record_id, snapshot)
        if table_name == "scoring_rubrics":
            return self._restore_rubric(tenant_id, record_id, snapshot)
        return self._restore_provider_config(tenant_id, record_id, snapshot)

    def _restore_prompt(
        self, tenant_id: UUID, record_id: Any, snapshot: dict[str, Any]
    ) -> PromptTemplate | None:
        for key, prompt in list(self.prompts.items()):
            if not (_same_uuid(prompt.id, record_id) and prompt.tenant_id == tenant_id):
                continue
            updates = {
                field: snapshot.get(field) for field in _ROLLBACK_FIELDS["prompt_templates"]
            }
            restored = prompt.model_copy(update=updates)
            del self.prompts[key]
            self.prompts[(restored.tenant_id, restored.key, restored.version)] = restored
            return restored
        return None

    def _restore_rubric(
        self, tenant_id: UUID, record_id: Any, snapshot: dict[str, Any]
    ) -> ScoringRubric | None:
        for key, rubric in list(self.rubrics.items()):
            if not (_same_uuid(rubric.id, record_id) and rubric.tenant_id == tenant_id):
                continue
            updates = {
                field: snapshot.get(field) for field in _ROLLBACK_FIELDS["scoring_rubrics"]
            }
            restored = rubric.model_copy(update=updates)
            del self.rubrics[key]
            self.rubrics[(restored.tenant_id, restored.key, restored.version)] = restored
            return restored
        return None

    def _restore_provider_config(
        self, tenant_id: UUID, record_id: Any, snapshot: dict[str, Any]
    ) -> ProviderConfig | None:
        for key, config in list(self.provider_configs.items()):
            if not (_same_uuid(config.id, record_id) and config.tenant_id == tenant_id):
                continue
            # ``version``/``updated_by`` are table columns that the Pydantic
            # model does not expose; only apply fields the model actually has.
            updates = {
                field: snapshot.get(field)
                for field in _ROLLBACK_FIELDS["provider_configs"]
                if field not in ("version", "updated_by")
            }
            restored = config.model_copy(update=updates)
            del self.provider_configs[key]
            self.provider_configs[
                (restored.tenant_id, restored.capability, restored.provider)
            ] = restored
            return restored
        return None

    # ------------------------------------------------------------------
    # Sources and leads
    # ------------------------------------------------------------------
    async def list_enabled_sources(self, tenant_id: UUID) -> list[GrowthSource]:
        rows = [
            source
            for source in self.sources
            if source.tenant_id == tenant_id and source.enabled
        ]
        return [
            source.model_copy(deep=True)
            for source in sorted(
                rows,
                key=lambda source: (
                    source.source_type,
                    source.platform,
                    source.id,
                ),
            )
        ]

    async def update_source_run(
        self,
        tenant_id: UUID,
        source_id: UUID,
        last_run_at: datetime,
        last_error: str | None = None,
    ) -> None:
        source = self._find_source(tenant_id, source_id)
        if source is None:
            return
        source.last_run_at = _aware(last_run_at)
        source.last_error = last_error

    async def upsert_lead(self, lead: NewSocialLead) -> tuple[SocialLead, bool]:
        existing = self._find_lead_by_dedupe(lead.tenant_id, lead.dedupe_key)
        if existing is not None:
            return existing.model_copy(deep=True), False

        clock = datetime.now(timezone.utc)
        data = lead.model_dump()
        data["published_at"] = _aware(lead.published_at)
        data.update(
            id=uuid4(),
            score=None,
            score_reasons=None,
            model=None,
            prompt_version=None,
            status="discovered",
            version=1,
            created_at=clock,
            updated_at=clock,
        )
        row = SocialLead(**data)
        self.leads.append(row.model_copy(deep=True))
        return row.model_copy(deep=True), True

    async def get_lead(
        self, tenant_id: UUID, lead_id: UUID
    ) -> SocialLead | None:
        lead = self._find_lead(tenant_id, lead_id)
        return None if lead is None else lead.model_copy(deep=True)

    async def list_leads(
        self, tenant_id: UUID, status: str | None = None, limit: int = 50
    ) -> list[SocialLead]:
        rows = [
            lead
            for lead in self.leads
            if lead.tenant_id == tenant_id
            and (status is None or lead.status == status)
        ]
        rows.sort(key=lambda lead: str(lead.id))
        rows.sort(key=lambda lead: _aware(lead.created_at), reverse=True)
        return [lead.model_copy(deep=True) for lead in rows[: int(limit)]]

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
        lead = self._find_lead(tenant_id, lead_id)
        if lead is None or lead.status != expected_status:
            return False
        lead.status = status
        if score is not None:
            lead.score = score
        if score_reasons is not None:
            lead.score_reasons = score_reasons
        if model is not None:
            lead.model = model
        if prompt_version is not None:
            lead.prompt_version = prompt_version
        lead.version += 1
        lead.updated_at = datetime.now(timezone.utc)
        return True

    # ------------------------------------------------------------------
    # Outreach messages and versions
    # ------------------------------------------------------------------
    async def create_message(self, message: NewOutreachMessage) -> OutreachMessage:
        existing = self._find_message_by_dedupe(message.tenant_id, message.dedupe_key)
        if existing is not None:
            return existing.model_copy(deep=True)

        clock = datetime.now(timezone.utc)
        data = message.model_dump()
        data["scheduled_at"] = _aware(message.scheduled_at)
        data.update(
            id=uuid4(),
            sent_at=None,
            provider_message_id=None,
            version=1,
            created_at=clock,
            updated_at=clock,
        )
        row = OutreachMessage(**data)
        self.messages.append(row.model_copy(deep=True))
        return row.model_copy(deep=True)

    async def get_message(
        self, tenant_id: UUID, message_id: UUID
    ) -> OutreachMessage | None:
        message = self._find_message(tenant_id, message_id)
        return None if message is None else message.model_copy(deep=True)

    async def list_messages(
        self, tenant_id: UUID, status: str | None = None, limit: int = 50
    ) -> list[OutreachMessage]:
        rows = [
            message
            for message in self.messages
            if message.tenant_id == tenant_id
            and (status is None or message.status == status)
        ]
        rows.sort(key=lambda message: str(message.id))
        rows.sort(key=lambda message: _aware(message.created_at), reverse=True)
        return [
            message.model_copy(deep=True) for message in rows[: int(limit)]
        ]

    async def find_message_by_dedupe_key(
        self, tenant_id: UUID, dedupe_key: str
    ) -> OutreachMessage | None:
        message = self._find_message_by_dedupe(tenant_id, dedupe_key)
        return None if message is None else message.model_copy(deep=True)

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
        message = self._find_message(tenant_id, message_id)
        if message is None or message.status != expected_status:
            return False
        message.status = status
        if sent_at is not None:
            message.sent_at = _aware(sent_at)
        if provider is not None:
            message.provider = provider
        if provider_message_id is not None:
            message.provider_message_id = provider_message_id
        if metadata_patch is not None:
            message.metadata = {**message.metadata, **metadata_patch}
        message.version += 1
        message.updated_at = datetime.now(timezone.utc)
        return True

    async def create_version(self, version: NewOutreachVersion) -> OutreachVersion:
        data = version.model_dump()
        data.update(
            id=uuid4(),
            approved_by=None,
            approved_at=None,
            created_at=datetime.now(timezone.utc),
        )
        row = OutreachVersion(**data)
        self.outreach_versions.append(row.model_copy(deep=True))
        return row.model_copy(deep=True)

    async def get_latest_version(
        self, tenant_id: UUID, message_id: UUID
    ) -> OutreachVersion | None:
        matches = [
            version
            for version in self.outreach_versions
            if version.tenant_id == tenant_id and version.message_id == message_id
        ]
        if not matches:
            return None
        return max(
            matches, key=lambda version: version.version
        ).model_copy(deep=True)

    async def mark_version_approved(
        self,
        tenant_id: UUID,
        version_id: UUID,
        approved_by: str,
        approved_at: datetime,
    ) -> None:
        version = next(
            (
                item
                for item in self.outreach_versions
                if item.tenant_id == tenant_id and item.id == version_id
            ),
            None,
        )
        if version is None:
            return
        version.approved_by = approved_by
        version.approved_at = _aware(approved_at)

    async def record_delivery(self, entry: NewDeliveryLog) -> None:
        self.deliveries.append(
            {
                "id": uuid4(),
                "created_at": datetime.now(timezone.utc),
                **entry.model_dump(),
            }
        )

    async def count_followups(
        self, tenant_id: UUID, original_message_id: UUID
    ) -> int:
        return sum(
            1
            for message in self.messages
            if message.tenant_id == tenant_id
            and str(message.metadata.get("followup_of")) == str(original_message_id)
        )

    async def latest_sent_at(
        self, tenant_id: UUID, lead_id: UUID
    ) -> datetime | None:
        sent = [
            _aware(message.sent_at)
            for message in self.messages
            if message.tenant_id == tenant_id
            and message.lead_id == lead_id
            and message.sent_at is not None
        ]
        return max(sent) if sent else None

    async def has_contacted_author(
        self,
        tenant_id: UUID,
        platform: str,
        author_public: str,
        exclude_message_id: UUID,
    ) -> bool:
        for message in self.messages:
            if message.tenant_id != tenant_id:
                continue
            if message.id == exclude_message_id:
                continue
            if message.status not in ("sent", "replied", "converted"):
                continue
            if "followup_of" in (message.metadata or {}):
                continue
            if message.lead_id is None:
                continue
            lead = self._find_lead(tenant_id, message.lead_id)
            if (
                lead is not None
                and lead.platform == platform
                and lead.author_public == author_public
            ):
                return True
        return False

    # ------------------------------------------------------------------
    # Approval requests
    # ------------------------------------------------------------------
    async def create_approval_request(
        self, request: NewApprovalRequest
    ) -> ApprovalRequest:
        existing = self._find_approval(request.tenant_id, request.approval_id)
        if existing is not None:
            return existing.model_copy(deep=True)

        clock = datetime.now(timezone.utc)
        data = request.model_dump()
        data.update(
            id=uuid4(),
            status="pending",
            decided_by=None,
            decided_at=None,
            reason=None,
            version=1,
            created_at=clock,
            updated_at=clock,
        )
        row = ApprovalRequest(**data)
        self.approvals.append(row.model_copy(deep=True))
        return row.model_copy(deep=True)

    async def get_approval_request(
        self, tenant_id: UUID, approval_id: str
    ) -> ApprovalRequest | None:
        approval = self._find_approval(tenant_id, approval_id)
        return (
            None if approval is None else approval.model_copy(deep=True)
        )

    async def decide_approval(
        self,
        tenant_id: UUID,
        approval_id: str,
        status: str,
        decided_by: str,
        reason: str = "",
    ) -> bool:
        approval = self._find_approval(tenant_id, approval_id)
        if approval is None or approval.status != "pending":
            return False
        clock = datetime.now(timezone.utc)
        approval.status = status
        approval.decided_by = decided_by
        approval.decided_at = clock
        approval.reason = reason
        approval.version += 1
        approval.updated_at = clock
        return True

    async def expire_pending_approvals(
        self, tenant_id: UUID, message_id: UUID
    ) -> int:
        clock = datetime.now(timezone.utc)
        expired = 0
        for approval in self.approvals:
            if (
                approval.tenant_id == tenant_id
                and approval.message_id == message_id
                and approval.status == "pending"
            ):
                approval.status = "expired"
                approval.decided_at = clock
                approval.version += 1
                approval.updated_at = clock
                expired += 1
        return expired

    async def set_approval_external_id(
        self, tenant_id: UUID, approval_id: str, external_id: str
    ) -> None:
        approval = self._find_approval(tenant_id, approval_id)
        if approval is None:
            return
        approval.external_id = external_id
        approval.updated_at = datetime.now(timezone.utc)

    # ------------------------------------------------------------------
    # Test-only helpers
    # ------------------------------------------------------------------
    def tasks_for(self, idempotency_key_prefix: str) -> list[PipelineTask]:
        """Tasks whose idempotency key starts with ``prefix``.

        Follow-up keys are compound (``followup:{original_id}:{message_id}``),
        so callers need prefix matching rather than exact equality.
        """
        return [
            task.model_copy(deep=True)
            for task in self.tasks
            if task.idempotency_key.startswith(idempotency_key_prefix)
        ]

    def outbox_for(self, idempotency_key: str) -> list[OutboxMessage]:
        return [
            row.model_copy(deep=True)
            for row in self.outbox
            if row.idempotency_key == idempotency_key
        ]

    def set_rate_counter(
        self,
        tenant_id: UUID,
        channel: str,
        scope: str,
        scope_key: str,
        window_start: datetime,
        count: int,
    ) -> None:
        self.counters[
            (tenant_id, channel, scope, scope_key, _aware(window_start))
        ] = count

    def truncate_all_for_tests(self) -> None:
        """Clear every store. Test-only; mirrors the Postgres helper.

        This fake helper is synchronous and must not be awaited (the Postgres
        version is ``async`` because it issues SQL).
        """
        for collection in (
            self.tasks,
            self.outbox,
            self.leads,
            self.messages,
            self.sources,
            self.approvals,
            self.outreach_versions,
            self.deliveries,
            self.audit,
        ):
            collection.clear()
        self.suppressions.clear()
        for mapping in (
            self.prompts,
            self.rubrics,
            self.provider_configs,
            self.rate_rules,
            self.features,
            self.versions,
            self.counters,
        ):
            mapping.clear()

    # ------------------------------------------------------------------
    # Internal lookup helpers
    # ------------------------------------------------------------------
    def _find_task(self, task_id: UUID) -> PipelineTask | None:
        return next((task for task in self.tasks if task.id == task_id), None)

    def _find_outbox(self, outbox_id: UUID) -> OutboxMessage | None:
        return next((row for row in self.outbox if row.id == outbox_id), None)

    def _find_source(
        self, tenant_id: UUID, source_id: UUID
    ) -> GrowthSource | None:
        return next(
            (
                source
                for source in self.sources
                if source.tenant_id == tenant_id and source.id == source_id
            ),
            None,
        )

    def _find_lead(self, tenant_id: UUID, lead_id: UUID) -> SocialLead | None:
        return next(
            (
                lead
                for lead in self.leads
                if lead.tenant_id == tenant_id and lead.id == lead_id
            ),
            None,
        )

    def _find_lead_by_dedupe(
        self, tenant_id: UUID, dedupe_key: str
    ) -> SocialLead | None:
        return next(
            (
                lead
                for lead in self.leads
                if lead.tenant_id == tenant_id and lead.dedupe_key == dedupe_key
            ),
            None,
        )

    def _find_message(
        self, tenant_id: UUID, message_id: UUID
    ) -> OutreachMessage | None:
        return next(
            (
                message
                for message in self.messages
                if message.tenant_id == tenant_id and message.id == message_id
            ),
            None,
        )

    def _find_message_by_dedupe(
        self, tenant_id: UUID, dedupe_key: str
    ) -> OutreachMessage | None:
        return next(
            (
                message
                for message in self.messages
                if message.tenant_id == tenant_id
                and message.dedupe_key == dedupe_key
            ),
            None,
        )

    def _find_approval(
        self, tenant_id: UUID, approval_id: str
    ) -> ApprovalRequest | None:
        return next(
            (
                approval
                for approval in self.approvals
                if approval.tenant_id == tenant_id
                and approval.approval_id == approval_id
            ),
            None,
        )


class FakeNotifier:
    """In-memory notifier that records every card it is asked to send."""

    def __init__(self) -> None:
        self.cards: list[dict] = []
        self.calls: list[tuple[str, dict]] = []

    async def send_card(self, chat_id: str, card: dict) -> str:
        self.calls.append((chat_id, card))
        self.cards.append(card)
        return f"fake-{len(self.cards)}"

    async def health(self):
        from growth_core.adapters.base import AdapterHealth

        return AdapterHealth(name="fake", status="ready")
