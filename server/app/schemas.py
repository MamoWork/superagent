from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from opportunity_core.models import (
    AuthKind,
    Capability,
    ProviderHealth,
    ProviderInfo,
    ProviderStatus,
    SearchQuery,
    Signal,
)

SavedStage = Literal[
    "saved", "validating", "contacted", "replied", "won", "dropped"
]


class ProviderErrorInfo(BaseModel):
    code: str
    message: str
    hint: str = ""
    retry_after_seconds: int | None = None


class RunCreate(BaseModel):
    workspace_id: str = "ws_default"
    domain_pack: str = "general"
    direction: str = Field(min_length=1, max_length=1000)
    keywords: list[str] = Field(default_factory=list)
    provider_ids: list[str] = Field(min_length=1)
    limit_per_provider: int = Field(default=20, ge=1, le=100)
    time_range_days: int | None = Field(default=90, ge=1)


class Run(BaseModel):
    id: str
    workspace_id: str
    domain_pack: str
    direction: str
    keywords: list[str] = Field(default_factory=list)
    provider_ids: list[str] = Field(default_factory=list)
    status: Literal["running", "completed", "partial", "failed"]
    stats: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    created_at: str
    finished_at: str | None = None
    has_analysis: bool = False
    signals: list[Signal] = Field(default_factory=list)


class ManualSignalCreate(BaseModel):
    provider_id: str = Field(default="manual", min_length=1)
    source_type: str = "post"
    source_url: str = Field(min_length=1)
    title: str = ""
    quote: str = ""
    author_public: str | None = None
    published_at: str | None = None
    metrics: dict[str, Any] = Field(default_factory=dict)


class EvidenceBrief(BaseModel):
    run_id: str
    status: str
    signal_count: int
    provider_counts: dict[str, int] = Field(default_factory=dict)
    provider_errors: dict[str, ProviderErrorInfo] = Field(default_factory=dict)
    top_signals: list[Signal] = Field(default_factory=list)
    pain_phrases: dict[str, int] = Field(default_factory=dict)
    note: str = ""


class Citation(BaseModel):
    """A pointer back to one collected signal. URLs are resolved server-side."""

    signal_id: str
    source_url: str = ""
    quote: str = ""
    note: str = ""


class DimensionScore(BaseModel):
    dimension_id: str
    name: str
    weight: float
    score: int = Field(ge=0, le=10)
    weighted_points: float = 0.0
    rationale: str = ""
    citations: list[Citation] = Field(default_factory=list)


class NextAction(BaseModel):
    action: str
    owner: Literal["user", "ai"] = "user"
    due_in_days: int | None = None


class OpportunityAnalysis(BaseModel):
    run_id: str
    domain_pack: str
    verdict: Literal["build", "verify", "drop"]
    score: int = Field(ge=0, le=100)
    one_liner: str
    thesis: str
    target_customer: str
    willingness_to_pay: str
    dimension_scores: list[DimensionScore] = Field(default_factory=list)
    next_actions: list[NextAction] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)
    model: str
    created_at: str


class AnalysisRequest(BaseModel):
    model: str | None = Field(
        default=None,
        description="覆盖本次分析的模型 ID，例如 gpt-4.1-mini 或 anthropic:claude-sonnet-4-5。",
    )


class ScheduleCreate(BaseModel):
    workspace_id: str = "ws_default"
    name: str = Field(default="", max_length=120)
    domain_pack: str = "general"
    direction: str = Field(min_length=1, max_length=1000)
    keywords: list[str] = Field(default_factory=list)
    provider_ids: list[str] = Field(min_length=1)
    limit_per_provider: int = Field(default=20, ge=1, le=100)
    time_range_days: int | None = Field(default=90, ge=1)
    cron: str = Field(
        default="0 9 * * *",
        description="标准 5 段 cron，例如每天 09:00 为 `0 9 * * *`。",
    )
    enabled: bool = True


class ScheduleUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=120)
    domain_pack: str | None = None
    direction: str | None = Field(default=None, min_length=1, max_length=1000)
    keywords: list[str] | None = None
    provider_ids: list[str] | None = Field(default=None, min_length=1)
    limit_per_provider: int | None = Field(default=None, ge=1, le=100)
    time_range_days: int | None = Field(default=None, ge=1)
    cron: str | None = None
    enabled: bool | None = None


class Schedule(BaseModel):
    id: str
    workspace_id: str
    name: str = ""
    domain_pack: str
    direction: str
    keywords: list[str] = Field(default_factory=list)
    provider_ids: list[str] = Field(default_factory=list)
    limit_per_provider: int = 20
    time_range_days: int | None = 90
    cron: str
    enabled: bool = True
    last_run_id: str | None = None
    last_run_at: str | None = None
    last_error: str | None = None
    created_at: str
    next_run_at: str | None = None


class AIStatus(BaseModel):
    configured: bool
    provider: str | None = None
    model: str | None = None
    base_url: str | None = None
    note: str = ""


class SavedOpportunity(BaseModel):
    """A stable snapshot of an analyzed opportunity, tracked locally."""

    run_id: str
    direction: str
    domain_pack: str
    title: str
    one_liner: str
    thesis: str
    score: int = Field(ge=0, le=100)
    verdict: Literal["build", "verify", "drop"]
    target_customer: str = ""
    willingness_to_pay: str = ""
    risks: list[str] = Field(default_factory=list)
    next_actions: list[NextAction] = Field(default_factory=list)
    dimension_scores: list[DimensionScore] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)
    stage: SavedStage = "saved"
    notes: str = ""
    created_at: str
    updated_at: str


class SavedOpportunityCreate(BaseModel):
    run_id: str = Field(min_length=1)
    stage: SavedStage = "saved"
    notes: str = Field(default="", max_length=5000)


class SavedOpportunityUpdate(BaseModel):
    stage: SavedStage | None = None
    notes: str | None = Field(default=None, max_length=5000)


class CitationDraft(BaseModel):
    signal_id: str = Field(description="必须来自输入信号列表中的 id，不得编造。")
    quote: str = Field(default="", description="原文中的短引用，最多 300 字。")


class DimensionDraft(BaseModel):
    dimension_id: str = Field(description="评分卡中的维度 id，例如 demand、margin。")
    score: int = Field(ge=0, le=10, description="0 到 10 分。")
    rationale: str = Field(description="给出该分数的证据理由。")
    citations: list[CitationDraft] = Field(default_factory=list)


class AnalysisDraft(BaseModel):
    """Structured output requested from the AI engine."""

    one_liner: str = Field(description="一句话机会判断，不超过 60 字。")
    thesis: str = Field(description="机会逻辑，说明为什么值得做或不值得做。")
    target_customer: str = Field(description="最具体的首批目标客户。")
    willingness_to_pay: str = Field(description="付费意愿判断及依据。")
    dimensions: list[DimensionDraft] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
