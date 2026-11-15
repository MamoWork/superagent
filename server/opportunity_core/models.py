from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

ProviderStatus = Literal[
    "ready", "needs_auth", "degraded", "disabled", "not_configured"
]
AuthKind = Literal["none", "browser", "api_key"]
Capability = Literal["search", "read", "comments", "profile", "trends"]


class ProviderInfo(BaseModel):
    id: str
    name: str
    group: str = "other"
    capabilities: list[Capability] = Field(default_factory=lambda: ["search"])
    auth: AuthKind = "none"
    status: ProviderStatus = "ready"
    cost: Literal["free", "byo_key", "paid"] = "free"
    rate_limit: dict[str, int] | None = None
    note: str | None = None


class ProviderHealth(BaseModel):
    id: str
    status: ProviderStatus
    detail: str = ""


class SearchQuery(BaseModel):
    text: str = Field(min_length=1, max_length=500)
    keywords: list[str] = Field(default_factory=list)
    limit: int = Field(default=20, ge=1, le=100)
    time_range_days: int | None = Field(default=90, ge=1)
    domain_pack: str = "general"
    backend: str | None = None


class Signal(BaseModel):
    id: str
    provider_id: str
    source_type: str = "post"
    source_url: str
    title: str = ""
    quote: str = ""
    author_public: str | None = None
    published_at: str | None = None
    metrics: dict[str, Any] = Field(default_factory=dict)
    # Raw provider payload is persisted but never returned by the API by default.
    raw: dict[str, Any] | None = Field(default=None, exclude=True)
