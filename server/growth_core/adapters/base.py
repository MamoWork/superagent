"""Shared adapter primitives: health status and the provider error hierarchy.

Every adapter failure is an :class:`AdapterError` (or a subclass). Error
messages are short, human-readable descriptions and must never contain
credentials, tokens, or authorization headers.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel

from growth_core.schemas import GrowthSource

__all__ = [
    "AdapterHealth",
    "AdapterError",
    "ProviderNotConfigured",
    "ProviderAuthError",
    "ProviderRateLimited",
    "ProviderTimeout",
    "ProviderUnavailable",
    "ProviderBadOutput",
    "RawPost",
    "SourceAdapter",
    "Notifier",
    "LLMClient",
    "SecretResolver",
]


@dataclass
class AdapterHealth:
    """Result of an adapter health probe.

    ``status`` is a short machine-readable state (for example ``"ready"``,
    ``"degraded"``, or ``"down"``). ``detail`` is an optional non-secret
    explanation suitable for logs and status endpoints.
    """

    name: str
    status: str
    detail: str = ""


class AdapterError(Exception):
    """Base class for adapter failures with a secret-free message."""

    def __init__(
        self,
        message: str = "",
        *,
        retry_after_seconds: int | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.retry_after_seconds = retry_after_seconds


class ProviderNotConfigured(AdapterError):
    """The provider is missing configuration or credentials."""


class ProviderAuthError(AdapterError):
    """The provider rejected the supplied credentials or token."""


class ProviderRateLimited(AdapterError):
    """The provider refused the request because of rate limiting."""


class ProviderTimeout(AdapterError):
    """The provider did not answer before the deadline."""


class ProviderUnavailable(AdapterError):
    """The provider failed, returned a server error, or was unreachable."""


class ProviderBadOutput(AdapterError):
    """The provider responded successfully but the payload was unusable."""


@dataclass(frozen=True)
class RawPost:
    """A platform post normalized into the shape the lead pipeline consumes."""

    platform: str
    platform_post_id: str
    title: str
    body: str
    author_public: str | None
    source_url: str
    published_at: datetime | None
    metrics: dict[str, Any]
    subreddit: str | None
    raw: dict[str, Any]


@runtime_checkable
class SourceAdapter(Protocol):
    """Contract for adapters that fetch posts from a social source."""

    name: str
    capabilities: dict[str, Any]

    async def fetch(self, source: GrowthSource) -> list[RawPost]: ...

    async def health(self) -> AdapterHealth: ...

    def validate_config(self) -> None: ...


@runtime_checkable
class Notifier(Protocol):
    """Contract for adapters that deliver cards to a chat channel."""

    async def send_card(self, chat_id: str, card: dict[str, Any]) -> str: ...

    async def health(self) -> AdapterHealth: ...


@runtime_checkable
class LLMClient(Protocol):
    """Contract for LLM adapters that return structured JSON output."""

    async def complete_json(
        self,
        *,
        system: str,
        user: str,
        schema: type[BaseModel],
        model: str | None = None,
    ) -> BaseModel: ...


@runtime_checkable
class SecretResolver(Protocol):
    """Resolve a secret reference (for example an env var name) to its value."""

    def get(self, ref: str | None) -> str: ...
