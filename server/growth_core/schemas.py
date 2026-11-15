"""Typed models shared by the Growth Agent repositories and services.

The ``New*`` models represent rows to be inserted. Status columns that are
NOT NULL in SQL but have a single well-defined initial value are injected by
the repository instead of being part of the insert model. ``NewOutreachMessage``
is the exception: drafting creates messages in several different statuses, so
the caller must supply ``status`` and the repository inserts it verbatim.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

__all__ = [
    "ApprovalRequest",
    "GrowthSource",
    "NewApprovalRequest",
    "NewAuditEntry",
    "NewDeliveryLog",
    "NewOutboxMessage",
    "NewOutreachMessage",
    "NewOutreachVersion",
    "NewSocialLead",
    "NewTask",
    "OutreachMessage",
    "OutreachVersion",
    "OutboxMessage",
    "PipelineTask",
    "PromptTemplate",
    "ProviderConfig",
    "RateLimitCheck",
    "RateLimitDecision",
    "RateLimitRule",
    "ScoringRubric",
    "SocialLead",
]


class NewTask(BaseModel):
    tenant_id: UUID
    workspace_id: UUID
    pipeline: str
    task_type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str
    priority: int = 100
    run_after: datetime | None = None
    max_attempts: int = 5


class PipelineTask(NewTask):
    id: UUID
    status: Literal["queued", "running", "succeeded", "failed", "dead"]
    run_after: datetime
    locked_at: datetime | None = None
    locked_by: str | None = None
    attempts: int = 0
    last_error: str | None = None
    created_at: datetime
    updated_at: datetime


class NewOutboxMessage(BaseModel):
    tenant_id: UUID
    workspace_id: UUID
    topic: str
    payload: dict[str, Any]
    idempotency_key: str
    next_attempt_at: datetime | None = None


class OutboxMessage(NewOutboxMessage):
    id: UUID
    status: Literal["pending", "sending", "sent", "failed", "dead"]
    attempts: int = 0
    next_attempt_at: datetime
    last_error: str | None = None
    created_at: datetime
    updated_at: datetime


class ProviderConfig(BaseModel):
    id: UUID | None = None
    tenant_id: UUID
    capability: str
    provider: str
    priority: int = 100
    enabled: bool = True
    config: dict[str, Any] = Field(default_factory=dict)
    secret_ref: str | None = None
    config_schema_version: int = 1


class PromptTemplate(BaseModel):
    id: UUID
    tenant_id: UUID
    key: str
    module: str
    version: int
    template: str
    user_template: str
    output_schema: dict[str, Any]
    model_hint: str | None = None
    enabled: bool = True


class ScoringRubric(BaseModel):
    id: UUID
    tenant_id: UUID
    key: str
    version: int
    dimensions: list[dict[str, Any]]
    penalties: list[dict[str, Any]]
    thresholds: dict[str, int]
    enabled: bool = True


class RateLimitRule(BaseModel):
    tenant_id: UUID
    channel: str
    scope: Literal["global", "platform", "subreddit", "user"]
    scope_key: str = "*"
    window_seconds: int
    max_count: int
    enabled: bool = True


class RateLimitCheck(BaseModel):
    channel: str = "social"
    scope: str
    scope_key: str
    max_count: int
    window_seconds: int


class RateLimitDecision(BaseModel):
    allowed: bool
    exceeded_scope: str | None = None
    exceeded_scope_key: str | None = None
    retry_after_seconds: int = 0


class NewAuditEntry(BaseModel):
    tenant_id: UUID
    workspace_id: UUID | None = None
    actor_type: Literal["user", "service", "n8n", "system"]
    actor_id: str | None = None
    action: str
    entity_type: str
    entity_id: UUID | None = None
    before: dict[str, Any] | None = None
    after: dict[str, Any] | None = None


class GrowthSource(BaseModel):
    id: UUID
    tenant_id: UUID
    workspace_id: UUID
    source_type: str
    platform: str
    dedupe_key: str
    config: dict[str, Any] = Field(default_factory=dict)
    cadence_minutes: int = 30
    enabled: bool = True
    last_run_at: datetime | None = None
    last_error: str | None = None
    version: int = 1


class NewSocialLead(BaseModel):
    tenant_id: UUID
    workspace_id: UUID
    source_id: UUID | None = None
    platform: str
    platform_post_id: str
    title: str = ""
    body: str = ""
    author_public: str | None = None
    source_url: str
    published_at: datetime | None = None
    metrics: dict[str, Any] = Field(default_factory=dict)
    raw: dict[str, Any] | None = None
    subreddit: str | None = None
    subreddit_rules: dict[str, Any] = Field(default_factory=dict)
    dedupe_key: str


class SocialLead(NewSocialLead):
    id: UUID
    score: int | None = None
    score_reasons: dict[str, Any] | None = None
    model: str | None = None
    prompt_version: str | None = None
    status: str
    version: int = 1
    created_at: datetime
    updated_at: datetime


class NewOutreachMessage(BaseModel):
    tenant_id: UUID
    workspace_id: UUID
    channel: str
    provider: str | None = None
    lead_id: UUID | None = None
    user_id: UUID | None = None
    rule_key: str | None = None
    status: str
    scheduled_at: datetime | None = None
    dedupe_key: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class OutreachMessage(NewOutreachMessage):
    id: UUID
    sent_at: datetime | None = None
    provider_message_id: str | None = None
    version: int = 1
    created_at: datetime
    updated_at: datetime


class NewOutreachVersion(BaseModel):
    tenant_id: UUID
    message_id: UUID
    version: int
    body_text: str
    subject: str | None = None
    cta_url: str | None = None
    model: str | None = None
    prompt_version: str | None = None
    risk_flags: list[str] = Field(default_factory=list)


class OutreachVersion(NewOutreachVersion):
    id: UUID
    approved_by: str | None = None
    approved_at: datetime | None = None
    created_at: datetime


class NewApprovalRequest(BaseModel):
    tenant_id: UUID
    workspace_id: UUID
    message_id: UUID
    approval_id: str
    provider: str = "feishu"
    external_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class ApprovalRequest(NewApprovalRequest):
    id: UUID
    status: Literal["pending", "approved", "rejected", "expired"]
    decided_by: str | None = None
    decided_at: datetime | None = None
    reason: str | None = None
    version: int = 1
    created_at: datetime
    updated_at: datetime


class NewDeliveryLog(BaseModel):
    tenant_id: UUID
    workspace_id: UUID
    message_id: UUID | None = None
    lead_id: UUID | None = None
    provider: str
    event_type: str
    payload: dict[str, Any] = Field(default_factory=dict)
