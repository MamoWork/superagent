from __future__ import annotations

import asyncio
from collections.abc import Iterable

from opportunity_core.models import ProviderHealth, ProviderInfo
from opportunity_core.providers.base import SourceProvider


class ProviderRegistry:
    def __init__(self, providers: Iterable[SourceProvider]) -> None:
        self._providers: dict[str, SourceProvider] = {p.info.id: p for p in providers}

    def list(self) -> list[ProviderInfo]:
        return [provider.info for provider in self._providers.values()]

    def get(self, provider_id: str) -> SourceProvider:
        try:
            return self._providers[provider_id]
        except KeyError as exc:
            raise KeyError(f"未知数据源：{provider_id}") from exc

    def ids(self) -> list[str]:
        return list(self._providers)

    async def health(self) -> list[ProviderHealth]:
        results = await asyncio.gather(
            *(provider.health() for provider in self._providers.values()),
            return_exceptions=True,
        )
        health: list[ProviderHealth] = []
        for provider, result in zip(self._providers.values(), results):
            if isinstance(result, ProviderHealth):
                health.append(result)
            else:
                health.append(
                    ProviderHealth(
                        id=provider.info.id,
                        status="degraded",
                        detail=str(result),
                    )
                )
        return health
