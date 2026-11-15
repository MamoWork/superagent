from __future__ import annotations

from app.config import Settings
from app.providers.agent_reach import AgentReachProvider
from app.providers.amazon_creators import AmazonCreatorsProvider
from app.providers.base import SourceProvider
from app.providers.google_trends import GoogleTrendsProvider
from app.providers.hackernews import HackerNewsProvider
from app.providers.rss import RssProvider
from opportunity_core.providers.registry import ProviderRegistry


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
