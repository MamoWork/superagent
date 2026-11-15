from __future__ import annotations

import asyncio
from types import SimpleNamespace

import httpx
import pytest

from app.config import Settings
from app.providers.amazon_creators import AmazonCreatorsProvider
from app.providers.base import ProviderError
from app.providers.google_trends import GoogleTrendsProvider
from app.providers.hackernews import HackerNewsProvider
from app.providers.registry import build_registry
from app.providers.rss import RssProvider
from app.schemas import SearchQuery

FEED = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
  <title>Indie News</title>
  <item>
    <title>Freelancers waste hours on invoices</title>
    <link>https://example.com/invoices</link>
    <description>&lt;p&gt;I still track payments in a spreadsheet.&lt;/p&gt;</description>
    <pubDate>Wed, 04 Nov 2026 10:00:00 GMT</pubDate>
    <category>freelance</category>
  </item>
  <item>
    <title>Old post</title>
    <link>https://example.com/old</link>
    <description>Too old</description>
    <pubDate>Mon, 01 Jan 2024 10:00:00 GMT</pubDate>
  </item>
</channel></rss>"""


def _rss_provider(handler, feeds=("https://example.com/feed.xml",)) -> RssProvider:
    return RssProvider(
        feeds,
        timeout=5,
        transport=httpx.MockTransport(handler),
    )


def test_rss_normalizes_and_filters_by_date() -> None:
    provider = _rss_provider(lambda request: httpx.Response(200, text=FEED))
    signals = asyncio.run(
        provider.search(SearchQuery(text="invoice", limit=10, time_range_days=30))
    )

    assert len(signals) == 1
    signal = signals[0]
    assert signal.provider_id == "rss"
    assert signal.source_type == "article"
    assert signal.source_url == "https://example.com/invoices"
    assert signal.quote == "I still track payments in a spreadsheet."
    assert signal.metrics["feed"] == "Indie News"
    assert signal.metrics["tags"] == ["freelance"]


def test_rss_filters_entries_by_query_terms() -> None:
    provider = _rss_provider(lambda request: httpx.Response(200, text=FEED))
    signals = asyncio.run(
        provider.search(SearchQuery(text="furniture", limit=10, time_range_days=3650))
    )
    assert signals == []


def test_rss_maps_rate_limit() -> None:
    provider = _rss_provider(lambda request: httpx.Response(429))
    with pytest.raises(ProviderError) as exc:
        asyncio.run(provider.search(SearchQuery(text="invoice", limit=5)))
    assert exc.value.code == "PROVIDER_RATE_LIMITED"


def test_rss_without_feeds_is_not_configured() -> None:
    provider = RssProvider(())
    assert provider.info.status == "not_configured"
    with pytest.raises(ProviderError) as exc:
        asyncio.run(provider.search(SearchQuery(text="invoice", limit=5)))
    assert exc.value.code == "PROVIDER_NOT_CONFIGURED"


def test_hackernews_normalizes_hits_and_falls_back_to_item_url() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["query"] == "invoice"
        assert "numericFilters" in request.url.params
        return httpx.Response(
            200,
            json={
                "hits": [
                    {
                        "objectID": "42",
                        "title": "Ask HN: invoice tool?",
                        "story_text": "I <em>hate</em> spreadsheets.",
                        "author": "alice",
                        "created_at": "2026-11-01T00:00:00Z",
                        "points": 12,
                        "num_comments": 4,
                    },
                    {"objectID": "43", "title": ""},
                ]
            },
        )

    provider = HackerNewsProvider(timeout=5, transport=httpx.MockTransport(handler))
    signals = asyncio.run(
        provider.search(SearchQuery(text="invoice", limit=5, time_range_days=30))
    )

    assert len(signals) == 1
    assert signals[0].source_url == "https://news.ycombinator.com/item?id=42"
    assert signals[0].quote == "I hate spreadsheets."
    assert signals[0].metrics["comments"] == 4


def test_hackernews_maps_rate_limit() -> None:
    provider = HackerNewsProvider(
        timeout=5,
        transport=httpx.MockTransport(lambda request: httpx.Response(429)),
    )
    with pytest.raises(ProviderError) as exc:
        asyncio.run(provider.search(SearchQuery(text="invoice", limit=5)))
    assert exc.value.code == "PROVIDER_RATE_LIMITED"


def test_google_trends_helpers() -> None:
    assert (
        GoogleTrendsProvider._keyword(
            SearchQuery(text="standing desk ecommerce trend")
        )
        == "standing desk"
    )
    assert (
        GoogleTrendsProvider._keyword(
            SearchQuery(text="anything", keywords=["electric standing desk"])
        )
        == "electric standing desk"
    )
    assert GoogleTrendsProvider._timeframe(30) == "today 1-m"
    assert GoogleTrendsProvider._timeframe(90) == "today 3-m"
    assert GoogleTrendsProvider._timeframe(365) == "today 12-m"
    assert GoogleTrendsProvider._timeframe(3650) == "today 5-y"
    assert GoogleTrendsProvider._relevant("electric standing desk", "standing desk")
    assert not GoogleTrendsProvider._relevant("netflix new releases", "standing desk")


def test_google_trends_missing_dependency_is_typed(monkeypatch) -> None:
    import app.providers.google_trends as module

    monkeypatch.setattr(module, "TrendReq", None)
    provider = GoogleTrendsProvider()
    assert provider.info.status == "not_configured"
    health = asyncio.run(provider.health())
    assert health.status == "not_configured"
    with pytest.raises(ProviderError) as exc:
        asyncio.run(provider.search(SearchQuery(text="desk", limit=5)))
    assert exc.value.code == "PROVIDER_NOT_CONFIGURED"


def test_amazon_requires_credentials() -> None:
    provider = AmazonCreatorsProvider()
    assert provider.info.status == "not_configured"
    health = asyncio.run(provider.health())
    assert health.status == "not_configured"
    with pytest.raises(ProviderError) as exc:
        asyncio.run(provider.search(SearchQuery(text="standing desk", limit=5)))
    assert exc.value.code == "PROVIDER_NEEDS_AUTH"


def test_amazon_normalizes_title_and_price() -> None:
    item = SimpleNamespace(
        item_info=SimpleNamespace(
            title=SimpleNamespace(display_value="Standing Desk Pro")
        ),
        offers_v2=SimpleNamespace(
            listings=[
                SimpleNamespace(
                    is_buy_box_winner=False,
                    price=SimpleNamespace(
                        money=SimpleNamespace(amount=199.99, currency="USD")
                    ),
                ),
                SimpleNamespace(
                    is_buy_box_winner=True,
                    price=SimpleNamespace(
                        money=SimpleNamespace(amount=179.99, currency="USD")
                    ),
                ),
            ]
        ),
    )
    assert AmazonCreatorsProvider._title(item) == "Standing Desk Pro"
    assert AmazonCreatorsProvider._price(item) == (179.99, "USD")


def test_registry_contains_optional_oss_providers() -> None:
    registry = build_registry(Settings())
    ids = set(registry.ids())
    assert {"rss", "hackernews", "google.trends", "amazon.creators"} <= ids
    assert registry.list()[0].id.startswith("agent-reach.")
