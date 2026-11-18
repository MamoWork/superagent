"""Repository protocol for the Growth Agent service layer."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any, Protocol, runtime_checkable
from uuid import UUID

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


@runtime_checkable
class GrowthRepository(Protocol):
    """Storage contract shared by the Postgres and in-memory repositories."""

    # Configuration reads -------------------------------------------------
    async def list_provider_configs(
        self, tenant_id: UUID, capability: str
    ) -> list[ProviderConfig]: ...

    async def get_prompt_template(
        self, tenant_id: UUID, key: str, version: int | None = None
    ) -> PromptTemplate | None: ...

    async def get_scoring_rubric(
        self, tenant_id: UUID, key: str, version: int | None = None
    ) -> ScoringRubric | None: ...

    async def get_feature(self, tenant_id: UUID, feature_key: str) -> bool: ...

    async def list_rate_limit_rules(
        self, tenant_id: UUID, channel: str
    ) -> list[RateLimitRule]: ...

    async def ensure_tenant(self, tenant_id: UUID, workspace_id: UUID) -> None: ...

    async def add_source(self, source: GrowthSource) -> None: ...

    async def close(self) -> None: ...

    # Pipeline tasks ------------------------------------------------------
    async def enqueue_task(self, task: NewTask) -> UUID: ...

    async def claim_task(
        self, worker_id: str, now: datetime | None = None
    ) -> PipelineTask | None: ...

    async def complete_task(
        self, task_id: UUID, worker_id: str | None = None
    ) -> None: ...

    async def fail_task(
        self,
        task_id: UUID,
        error: str,
        now: datetime | None = None,
        worker_id: str | None = None,
    ) -> None: ...

    async def reclaim_stale_tasks(
        self, older_than_seconds: int, now: datetime | None = None
    ) -> int: ...

    # Transactional outbox ------------------------------------------------
    async def enqueue_outbox(self, message: NewOutboxMessage) -> UUID: ...

    async def claim_outbox(
        self, limit: int = 10, now: datetime | None = None
    ) -> list[OutboxMessage]: ...

    async def mark_outbox_sent(self, outbox_id: UUID) -> None: ...

    async def mark_outbox_failed(
        self, outbox_id: UUID, error: str, now: datetime | None = None
    ) -> None: ...

    # Rate limits, suppression, audit, config rollback --------------------
    async def consume_rate_limits(
        self,
        tenant_id: UUID,
        checks: Sequence[RateLimitCheck],
        now: datetime | None = None,
    ) -> RateLimitDecision: ...

    async def is_suppressed(self, tenant_id: UUID, kind: str, value: str) -> bool: ...

    async def add_suppression(
        self,
        tenant_id: UUID,
        kind: str,
        value: str,
        reason: str,
        source: str = "",
    ) -> None: ...

    async def write_audit(self, entry: NewAuditEntry) -> None: ...

    async def rollback_config_version(
        self, tenant_id: UUID, version_id: UUID, changed_by: str
    ) -> bool: ...

    # Sources and leads ---------------------------------------------------
    async def list_enabled_sources(self, tenant_id: UUID) -> list[GrowthSource]: ...

    async def update_source_run(
        self,
        tenant_id: UUID,
        source_id: UUID,
        last_run_at: datetime,
        last_error: str | None = None,
    ) -> None: ...

    async def upsert_lead(self, lead: NewSocialLead) -> tuple[SocialLead, bool]: ...

    async def get_lead(self, tenant_id: UUID, lead_id: UUID) -> SocialLead | None: ...

    async def list_leads(
        self, tenant_id: UUID, status: str | None = None, limit: int = 50
    ) -> list[SocialLead]: ...

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
    ) -> bool: ...

    # Outreach messages and versions -------------------------------------
    async def create_message(
        self, message: NewOutreachMessage
    ) -> OutreachMessage: ...

    async def get_message(
        self, tenant_id: UUID, message_id: UUID
    ) -> OutreachMessage | None: ...

    async def list_messages(
        self, tenant_id: UUID, status: str | None = None, limit: int = 50
    ) -> list[OutreachMessage]: ...

    async def find_message_by_dedupe_key(
        self, tenant_id: UUID, dedupe_key: str
    ) -> OutreachMessage | None: ...

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
    ) -> bool: ...

    async def create_version(self, version: NewOutreachVersion) -> OutreachVersion: ...

    async def get_latest_version(
        self, tenant_id: UUID, message_id: UUID
    ) -> OutreachVersion | None: ...

    async def mark_version_approved(
        self,
        tenant_id: UUID,
        version_id: UUID,
        approved_by: str,
        approved_at: datetime,
    ) -> None: ...

    async def record_delivery(self, entry: NewDeliveryLog) -> None: ...

    async def count_followups(
        self, tenant_id: UUID, original_message_id: UUID
    ) -> int: ...

    async def latest_sent_at(
        self, tenant_id: UUID, lead_id: UUID
    ) -> datetime | None: ...

    async def has_contacted_author(
        self,
        tenant_id: UUID,
        platform: str,
        author_public: str,
        exclude_message_id: UUID,
    ) -> bool:
        """Whether an original message already reached this platform author.

        Only original messages (not follow-ups) whose status is ``sent``,
        ``replied``, or ``converted`` count. ``exclude_message_id`` lets the
        caller ignore the message being marked.
        """
        ...

    # Approval requests ---------------------------------------------------
    async def create_approval_request(
        self, request: NewApprovalRequest
    ) -> ApprovalRequest: ...

    async def get_approval_request(
        self, tenant_id: UUID, approval_id: str
    ) -> ApprovalRequest | None: ...

    async def decide_approval(
        self,
        tenant_id: UUID,
        approval_id: str,
        status: str,
        decided_by: str,
        reason: str = "",
    ) -> bool: ...

    async def expire_pending_approvals(
        self, tenant_id: UUID, message_id: UUID
    ) -> int: ...

    async def set_approval_external_id(
        self, tenant_id: UUID, approval_id: str, external_id: str
    ) -> None: ...
