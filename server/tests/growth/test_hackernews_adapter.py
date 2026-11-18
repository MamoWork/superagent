"""Tests for the Hacker News source adapter."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import uuid4

import httpx
import pytest

from growth_core.adapters.base import (
    AdapterHealth,
    ProviderAuthError,
    ProviderBadOutput,
    ProviderNotConfigured,
    ProviderRateLimited,
    ProviderUnavailable,
)
from growth_core.adapters.registry import AdapterRegistry, EnvSecretResolver
from growth_core.schemas import GrowthSource, ProviderConfig
from growth_social.adapters.hackernews import HackerNewsAdapter


def _source(config: dict) -> GrowthSource:
    return GrowthSource(
        id=uuid4(),
        tenant_id=uuid4(),
        workspace_id=uuid4(),
        source_type="hackernews",
        platform="hackernews",
        dedupe_key="hn:churn",
        config=config,
        cadence_minutes=30,
        enabled=True,
    )


def _hit(**overrides) -> dict:
    hit = {
        "objectID": "123",
        "title": "Ask HN: How do you track customer churn?",
        "story_text": "We use a spreadsheet and it is painful.",
        "author": "pg",
        "url": "https://example.com/post",
        "created_at_i": 1700000000,
        "points": 42,
        "num_comments": 7,
    }
    hit.update(overrides)
    return hit


def _client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def _ok_handler(payload: dict):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    return handler


# ---------------------------------------------------------------------------
# Fetching and normalization
# ---------------------------------------------------------------------------


async def test_hackernews_maps_algolia_hits():
    payload = {"hits": [_hit()]}

    def handler(request: httpx.Request) -> httpx.Response:
        assert "query=churn" in str(request.url)
        return httpx.Response(200, json=payload)

    client = _client(handler)
    adapter = HackerNewsAdapter(client=client)

    posts = await adapter.fetch(_source({"query": "churn", "limit": 10}))

    assert len(posts) == 1
    post = posts[0]
    assert post.platform == "hackernews"
    assert post.platform_post_id == "123"
    assert post.title == "Ask HN: How do you track customer churn?"
    assert post.body == "We use a spreadsheet and it is painful."
    assert post.author_public == "pg"
    assert post.source_url == "https://example.com/post"
    assert post.subreddit is None
    assert post.metrics == {"points": 42, "comments": 7}
    assert post.published_at == datetime(
        2023, 11, 14, 22, 13, 20, tzinfo=timezone.utc
    )
    assert post.raw["objectID"] == "123"
    await client.aclose()


async def test_hackernews_missing_url_falls_back_to_item_link():
    payload = {"hits": [_hit(url=None)]}
    client = _client(_ok_handler(payload))
    adapter = HackerNewsAdapter(client=client)

    posts = await adapter.fetch(_source({"query": "churn"}))

    assert posts[0].source_url == "https://news.ycombinator.com/item?id=123"
    await client.aclose()


async def test_hackernews_body_falls_back_to_comment_text():
    payload = {"hits": [_hit(story_text=None, comment_text="reply body")]}
    client = _client(_ok_handler(payload))
    adapter = HackerNewsAdapter(client=client)

    posts = await adapter.fetch(_source({"query": "churn"}))

    assert posts[0].body == "reply body"
    await client.aclose()


async def test_hackernews_non_string_story_text_falls_back_to_comment_text():
    # A non-string ``story_text`` is treated as absent, so the valid
    # ``comment_text`` must still be used as the body.
    payload = {"hits": [_hit(story_text=5, comment_text="reply body")]}
    client = _client(_ok_handler(payload))
    adapter = HackerNewsAdapter(client=client)

    posts = await adapter.fetch(_source({"query": "churn"}))

    assert posts[0].body == "reply body"
    await client.aclose()


async def test_hackernews_body_defaults_to_empty_string():
    payload = {"hits": [_hit(story_text=None, comment_text=None)]}
    client = _client(_ok_handler(payload))
    adapter = HackerNewsAdapter(client=client)

    posts = await adapter.fetch(_source({"query": "churn"}))

    assert posts[0].body == ""
    await client.aclose()


async def test_hackernews_skips_malformed_hits():
    payload = {
        "hits": [
            "not-a-dict",
            None,
            {},
            {"objectID": ""},
            {
                "objectID": "partial",
                "title": 123,
                "story_text": 5,
                "comment_text": ["x"],
                "author": 7,
                "url": 9,
            },
            _hit(objectID="good"),
        ]
    }
    client = _client(_ok_handler(payload))
    adapter = HackerNewsAdapter(client=client)

    posts = await adapter.fetch(_source({"query": "churn"}))

    assert [post.platform_post_id for post in posts] == ["partial", "good"]
    partial = posts[0]
    assert partial.title == ""
    assert partial.body == ""
    assert partial.author_public is None
    assert partial.source_url == "https://news.ycombinator.com/item?id=partial"
    assert partial.metrics == {"points": 0, "comments": 0}
    await client.aclose()


async def test_hackernews_missing_created_at_i_gives_none():
    hit = _hit()
    del hit["created_at_i"]
    client = _client(_ok_handler({"hits": [hit]}))
    adapter = HackerNewsAdapter(client=client)

    posts = await adapter.fetch(_source({"query": "churn"}))

    assert posts[0].published_at is None
    await client.aclose()


@pytest.mark.parametrize(
    "created_at_i",
    [None, "not-a-number", float("inf"), 10**30, {}, -10**30],
)
async def test_hackernews_bad_created_at_i_does_not_abort_fetch(created_at_i):
    payload = {"hits": [_hit(created_at_i=created_at_i), _hit(objectID="ok")]}
    # Python's json.loads accepts the non-standard ``Infinity`` literal, so
    # send it raw rather than through httpx's ``json=`` encoder (which rejects
    # non-finite floats).
    body = json.dumps(payload, allow_nan=True).encode()
    client = _client(
        lambda request: httpx.Response(
            200, content=body, headers={"content-type": "application/json"}
        )
    )
    adapter = HackerNewsAdapter(client=client)

    posts = await adapter.fetch(_source({"query": "churn"}))

    assert [post.platform_post_id for post in posts] == ["123", "ok"]
    assert posts[0].published_at is None
    assert posts[1].published_at == datetime(
        2023, 11, 14, 22, 13, 20, tzinfo=timezone.utc
    )
    await client.aclose()


async def test_hackernews_request_targets_search_by_date_with_params():
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["params"] = dict(request.url.params)
        return httpx.Response(200, json={"hits": []})

    client = _client(handler)
    adapter = HackerNewsAdapter(client=client, base_url="https://hn.example")

    posts = await adapter.fetch(_source({"query": "churn", "limit": 10}))

    assert posts == []
    assert seen["path"] == "/api/v1/search_by_date"
    assert seen["params"] == {
        "query": "churn",
        "tags": "story",
        "hitsPerPage": "10",
    }
    await client.aclose()


@pytest.mark.parametrize(
    ("configured", "expected"),
    [(None, "25"), (500, "100"), (0, "1"), (100, "100"), (1, "1")],
)
async def test_hackernews_limit_defaults_and_clamps(configured, expected):
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["limit"] = request.url.params["hitsPerPage"]
        return httpx.Response(200, json={"hits": []})

    client = _client(handler)
    adapter = HackerNewsAdapter(client=client)
    config = {"query": "churn"}
    if configured is not None:
        config["limit"] = configured

    await adapter.fetch(_source(config))

    assert seen["limit"] == expected
    await client.aclose()


# ---------------------------------------------------------------------------
# Configuration validation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "config",
    [{}, {"query": None}, {"query": ""}, {"query": "   "}],
)
async def test_hackernews_missing_query_raises_bad_config(config):
    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        raise AssertionError("fetch must not make a request without a query")

    client = _client(handler)
    adapter = HackerNewsAdapter(client=client)

    with pytest.raises(ProviderNotConfigured) as excinfo:
        await adapter.fetch(_source(config))

    assert str(excinfo.value) == "PROVIDER_NOT_CONFIGURED: hackernews query"
    await client.aclose()


@pytest.mark.parametrize("limit", ["ten", 1.5, True, False])
async def test_hackernews_invalid_limit_raises_bad_config(limit):
    client = _client(_ok_handler({"hits": []}))
    adapter = HackerNewsAdapter(client=client)

    with pytest.raises(ProviderNotConfigured) as excinfo:
        await adapter.fetch(_source({"query": "churn", "limit": limit}))

    assert str(excinfo.value) == "PROVIDER_NOT_CONFIGURED: hackernews limit"
    await client.aclose()


# ---------------------------------------------------------------------------
# Error mapping
# ---------------------------------------------------------------------------


async def test_hackernews_429_raises_rate_limited():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, headers={"Retry-After": "120"})

    client = _client(handler)
    adapter = HackerNewsAdapter(client=client)

    with pytest.raises(ProviderRateLimited) as excinfo:
        await adapter.fetch(_source({"query": "churn"}))

    assert str(excinfo.value) == "PROVIDER_RATE_LIMITED: hackernews rate limited"
    assert excinfo.value.retry_after_seconds == 120
    await client.aclose()


async def test_hackernews_429_without_retry_after_has_none():
    client = _client(lambda request: httpx.Response(429))
    adapter = HackerNewsAdapter(client=client)

    with pytest.raises(ProviderRateLimited) as excinfo:
        await adapter.fetch(_source({"query": "churn"}))

    assert str(excinfo.value) == "PROVIDER_RATE_LIMITED: hackernews rate limited"
    assert excinfo.value.retry_after_seconds is None
    await client.aclose()


@pytest.mark.parametrize("status", [401, 403])
async def test_hackernews_auth_errors(status):
    client = _client(lambda request: httpx.Response(status))
    adapter = HackerNewsAdapter(client=client)

    with pytest.raises(ProviderAuthError):
        await adapter.fetch(_source({"query": "churn"}))

    await client.aclose()


async def test_hackernews_404_raises_not_configured():
    client = _client(lambda request: httpx.Response(404))
    adapter = HackerNewsAdapter(client=client)

    with pytest.raises(ProviderNotConfigured) as excinfo:
        await adapter.fetch(_source({"query": "churn"}))

    assert str(excinfo.value) == (
        "PROVIDER_NOT_CONFIGURED: hackernews endpoint may not exist"
    )
    await client.aclose()


@pytest.mark.parametrize("status", [500, 503])
async def test_hackernews_server_errors_raise_unavailable(status):
    client = _client(lambda request: httpx.Response(status))
    adapter = HackerNewsAdapter(client=client)

    with pytest.raises(ProviderUnavailable):
        await adapter.fetch(_source({"query": "churn"}))

    await client.aclose()


async def test_hackernews_other_non_200_raises_unavailable():
    client = _client(lambda request: httpx.Response(418))
    adapter = HackerNewsAdapter(client=client)

    with pytest.raises(ProviderUnavailable):
        await adapter.fetch(_source({"query": "churn"}))

    await client.aclose()


async def test_hackernews_status_is_checked_before_json_parsing():
    # A 500 with a non-JSON body must map to ProviderUnavailable, not
    # ProviderBadOutput.
    client = _client(
        lambda request: httpx.Response(
            500, content=b"not-json", headers={"content-type": "text/plain"}
        )
    )
    adapter = HackerNewsAdapter(client=client)

    with pytest.raises(ProviderUnavailable):
        await adapter.fetch(_source({"query": "churn"}))

    await client.aclose()


async def test_hackernews_timeout_raises_unavailable():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    client = _client(handler)
    adapter = HackerNewsAdapter(client=client)

    with pytest.raises(ProviderUnavailable):
        await adapter.fetch(_source({"query": "churn"}))

    await client.aclose()


async def test_hackernews_invalid_json_raises_bad_output():
    client = _client(
        lambda request: httpx.Response(
            200,
            content=b"not-json",
            headers={"content-type": "application/json"},
        )
    )
    adapter = HackerNewsAdapter(client=client)

    with pytest.raises(ProviderBadOutput):
        await adapter.fetch(_source({"query": "churn"}))

    await client.aclose()


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {},
        {"hits": None},
        {"hits": "nope"},
        {"hits": {}},
    ],
)
async def test_hackernews_bad_payload_shape_raises_bad_output(payload):
    client = _client(_ok_handler(payload))
    adapter = HackerNewsAdapter(client=client)

    with pytest.raises(ProviderBadOutput):
        await adapter.fetch(_source({"query": "churn"}))

    await client.aclose()


# ---------------------------------------------------------------------------
# Health, ownership, and construction from config
# ---------------------------------------------------------------------------


async def test_hackernews_health_is_ready_without_network():
    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        raise AssertionError("health must not make a network call")

    client = _client(handler)
    adapter = HackerNewsAdapter(client=client)

    health = await adapter.health()

    assert health == AdapterHealth(name="hackernews", status="ready")
    await client.aclose()


async def test_hackernews_aclose_leaves_supplied_client_open():
    client = httpx.AsyncClient()
    adapter = HackerNewsAdapter(client=client)

    await adapter.aclose()

    assert client.is_closed is False
    await client.aclose()


async def test_hackernews_from_config_closes_own_client():
    config = ProviderConfig(
        tenant_id=uuid4(),
        capability="social_source",
        provider="hackernews",
        config={},
    )
    adapter = HackerNewsAdapter.from_config(config, EnvSecretResolver())

    assert adapter._base_url == "https://hn.algolia.com"
    await adapter.aclose()

    assert adapter._client.is_closed is True


async def test_hackernews_from_config_reads_base_url():
    config = ProviderConfig(
        tenant_id=uuid4(),
        capability="social_source",
        provider="hackernews",
        config={"base_url": "https://hn.example"},
    )

    adapter = HackerNewsAdapter.from_config(config, EnvSecretResolver())

    assert adapter._base_url == "https://hn.example"
    await adapter.aclose()


# ---------------------------------------------------------------------------
# Registry integration
# ---------------------------------------------------------------------------


def test_registry_resolves_hackernews_adapter_from_config():
    config = ProviderConfig(
        tenant_id=uuid4(),
        capability="social_source",
        provider="hackernews",
        priority=10,
        enabled=True,
        config={},
        secret_ref=None,
    )

    adapter = AdapterRegistry([config], EnvSecretResolver()).source("hackernews")

    assert isinstance(adapter, HackerNewsAdapter)
    import asyncio

    asyncio.run(adapter.aclose())
