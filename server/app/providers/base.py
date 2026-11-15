from __future__ import annotations

from abc import ABC, abstractmethod

from app.schemas import ProviderHealth, ProviderInfo, SearchQuery, Signal


class ProviderError(Exception):
    """A normalized provider failure. The core never sees platform-specific errors."""

    def __init__(
        self,
        code: str,
        message: str,
        hint: str = "",
        retry_after_seconds: int | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.hint = hint
        self.retry_after_seconds = retry_after_seconds


class SourceProvider(ABC):
    """Every data source implements this interface.

    The core and the UI only depend on this contract. An adapter is the only
    place allowed to know how a specific tool is invoked (CLI, HTTP, MCP, ...).
    """

    info: ProviderInfo

    @abstractmethod
    async def health(self) -> ProviderHealth:
        raise NotImplementedError

    @abstractmethod
    async def search(self, query: SearchQuery) -> list[Signal]:
        raise NotImplementedError
