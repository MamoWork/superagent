from __future__ import annotations

import asyncio
from collections.abc import Iterable

from app.config import Settings
from app.providers.agent_reach import AgentReachProvider
from app.providers.amazon_creators import AmazonCreatorsProvider
from app.providers.base import SourceProvider
from app.providers.google_trends import GoogleTrendsProvider
from app.providers.hackernews import HackerNewsProvider
from app.providers.rss import RssProvider
from app.schemas import ProviderHealth, ProviderInfo


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


def build_registry(settings: Settings) -> ProviderRegistry:
    providers: list[SourceProvider] = []
    for channel in settings.agent_reach_channels:
        providers.append(
            AgentReachProvider(
                channel=channel,
                bin_path=settings.agent_reach_bin,
                timeout=settings.agent_reach_timeout,
            )
        )
    providers.append(RssProvider(settings.rss_feeds, timeout=settings.http_timeout))
    providers.append(HackerNewsProvider(timeout=settings.http_timeout))
    providers.append(
        GoogleTrendsProvider(geo=settings.trends_geo, timeout=settings.http_timeout)
    )
    providers.append(
        AmazonCreatorsProvider(
            credential_id=settings.amazon_credential_id,
            credential_secret=settings.amazon_credential_secret,
            tag=settings.amazon_tag,
            version=settings.amazon_version,
            country=settings.amazon_country,
            timeout=settings.http_timeout,
        )
    )
    return ProviderRegistry(providers)
