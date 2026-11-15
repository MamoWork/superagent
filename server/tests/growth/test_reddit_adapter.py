"""Tests for the Reddit source adapter."""

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
from growth_social.adapters.reddit import RedditAdapter


def _source(config: dict) -> GrowthSource:
    return GrowthSource(
        id=uuid4(),
        tenant_id=uuid4(),
        workspace_id=uuid4(),
        source_type="reddit",
        platform="reddit",
        dedupe_key="reddit:r/saas",
        config=config,
        cadence_minutes=30,
        enabled=True,
    )


def _child(**overrides) -> dict:
    data = {
        "id": "a1",
        "title": "How do I track SaaS churn?",
        "selftext": "manual spreadsheet",
        "author": "u/x",
        "permalink": "/r/saas/comments/a1/x/",
        "created_utc": 1700000000,
        "score": 3,
        "num_comments": 2,
        "subreddit": "saas",
        "stickied": False,
    }
    data.update(overrides)
    return {"data": data}


def _client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def _ok_handler(payload: dict):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    return handler


# ---------------------------------------------------------------------------
# Fetching and normalization
# ---------------------------------------------------------------------------


async def test_reddit_fetches_and_filters_keywords():
    payload = {
        "data": {
            "children": [
                _child(),
                _child(
                    id="a2",
                    title="Weekly promo",
                    selftext="",
                    author="u/y",
                    permalink="/r/saas/comments/a2/y/",
                    score=0,
                    num_comments=0,
                ),
            ]
        }
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["user-agent"] == "test-agent"
        return httpx.Response(200, json=payload)

    client = _client(handler)
    adapter = RedditAdapter(client=client, user_agent="test-agent")
    posts = await adapter.fetch(
        _source({"subreddit": "saas", "keywords": ["churn"], "limit": 10})
    )

    assert len(posts) == 1
    post = posts[0]
    assert post.platform == "reddit"
    assert post.platform_post_id == "a1"
    assert post.title == "How do I track SaaS churn?"
    assert post.body == "manual spreadsheet"
    assert post.author_public == "u/x"
    assert post.source_url == "https://www.reddit.com/r/saas/comments/a1/x/"
    assert post.subreddit == "saas"
    assert post.metrics == {"score": 3, "comments": 2}
    assert post.published_at == datetime(2023, 11, 14, 22, 13, 20, tzinfo=timezone.utc)
    assert post.raw["id"] == "a1"
    await client.aclose()


async def test_reddit_skips_stickied_posts():
    payload = {
        "data": {
            "children": [
                _child(id="sticky", stickied=True),
                _child(id="normal", title="We need a CRM", selftext=""),
            ]
        }
    }
    client = _client(_ok_handler(payload))
    adapter = RedditAdapter(client=client, user_agent="test-agent")

    posts = await adapter.fetch(_source({"subreddit": "saas"}))

    assert [post.platform_post_id for post in posts] == ["normal"]
    await client.aclose()


async def test_reddit_skips_malformed_children():
    payload = {
        "data": {
            "children": [
                "not-a-dict",
                {"data": "not-a-dict"},
                {"data": {"id": "no-permalink", "title": "x", "selftext": ""}},
                {"data": {"permalink": "/r/saas/comments/noid/", "title": "x"}},
                {"data": None},
                _child(id="good"),
            ]
        }
    }
    client = _client(_ok_handler(payload))
    adapter = RedditAdapter(client=client, user_agent="test-agent")

    posts = await adapter.fetch(_source({"subreddit": "saas"}))

    assert [post.platform_post_id for post in posts] == ["good"]
    await client.aclose()


async def test_reddit_missing_created_utc_gives_none():
    payload = {"data": {"children": [_child(created_utc=None)]}}
    client = _client(_ok_handler(payload))
    adapter = RedditAdapter(client=client, user_agent="test-agent")

    posts = await adapter.fetch(_source({"subreddit": "saas"}))

    assert posts[0].published_at is None
    await client.aclose()


async def test_reddit_out_of_range_created_utc_does_not_abort_fetch():
    payload = {
        "data": {
            "children": [
                _child(id="inf", created_utc=float("inf")),
                _child(id="ok"),
            ]
        }
    }
    # Python's json.loads accepts the non-standard ``Infinity`` literal, so
    # send it raw rather than through httpx's ``json=`` encoder (which rejects
    # non-finite floats).
    body = json.dumps(payload, allow_nan=True).encode()
    client = _client(
        lambda request: httpx.Response(
            200, content=body, headers={"content-type": "application/json"}
        )
    )
    adapter = RedditAdapter(client=client, user_agent="test-agent")

    posts = await adapter.fetch(_source({"subreddit": "saas"}))

    assert [post.platform_post_id for post in posts] == ["inf", "ok"]
    assert posts[0].published_at is None
    assert posts[1].published_at == datetime(
        2023, 11, 14, 22, 13, 20, tzinfo=timezone.utc
    )
    await client.aclose()


async def test_reddit_request_targets_new_json_and_sends_limit():
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["limit"] = request.url.params["limit"]
        return httpx.Response(200, json={"data": {"children": []}})

    client = _client(handler)
    adapter = RedditAdapter(
        client=client,
        user_agent="test-agent",
        base_url="https://reddit.example",
    )

    posts = await adapter.fetch(_source({"subreddit": "saas", "limit": 10}))

    assert posts == []
    assert seen["path"] == "/r/saas/new.json"
    assert seen["limit"] == "10"
    await client.aclose()


@pytest.mark.parametrize(
    ("configured", "expected"),
    [(None, "25"), (500, "100"), (0, "1"), (100, "100"), (1, "1")],
)
async def test_reddit_limit_defaults_and_clamps(configured, expected):
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["limit"] = request.url.params["limit"]
        return httpx.Response(200, json={"data": {"children": []}})

    client = _client(handler)
    adapter = RedditAdapter(client=client, user_agent="test-agent")
    config = {"subreddit": "saas"}
    if configured is not None:
        config["limit"] = configured

    await adapter.fetch(_source(config))

    assert seen["limit"] == expected
    await client.aclose()


# ---------------------------------------------------------------------------
# Configuration validation
# ---------------------------------------------------------------------------


async def test_reddit_missing_subreddit_raises_bad_config():
    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        raise AssertionError("fetch must not make a request without a subreddit")

    client = _client(handler)
    adapter = RedditAdapter(client=client, user_agent="test-agent")

    with pytest.raises(ProviderNotConfigured) as excinfo:
        await adapter.fetch(_source({}))

    assert str(excinfo.value) == "PROVIDER_NOT_CONFIGURED: reddit subreddit"
    await client.aclose()


async def test_reddit_non_int_limit_raises_bad_config():
    client = _client(_ok_handler({"data": {"children": []}}))
    adapter = RedditAdapter(client=client, user_agent="test-agent")

    with pytest.raises(ProviderNotConfigured) as excinfo:
        await adapter.fetch(_source({"subreddit": "saas", "limit": "ten"}))

    assert str(excinfo.value) == "PROVIDER_NOT_CONFIGURED: reddit limit"
    await client.aclose()


async def test_reddit_non_list_keywords_raises_bad_config():
    client = _client(_ok_handler({"data": {"children": []}}))
    adapter = RedditAdapter(client=client, user_agent="test-agent")

    with pytest.raises(ProviderNotConfigured) as excinfo:
        await adapter.fetch(_source({"subreddit": "saas", "keywords": "churn"}))

    assert str(excinfo.value) == "PROVIDER_NOT_CONFIGURED: reddit keywords"
    await client.aclose()


def test_reddit_constructor_rejects_empty_user_agent():
    client = httpx.AsyncClient()

    with pytest.raises(ProviderNotConfigured) as excinfo:
        RedditAdapter(client=client, user_agent="")

    assert str(excinfo.value) == ("PROVIDER_NOT_CONFIGURED: reddit user_agent")
    import asyncio

    asyncio.run(client.aclose())


# ---------------------------------------------------------------------------
# Error mapping
# ---------------------------------------------------------------------------


async def test_reddit_429_raises_rate_limited():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, headers={"Retry-After": "120"})

    client = _client(handler)
    adapter = RedditAdapter(client=client, user_agent="test-agent")

    with pytest.raises(ProviderRateLimited) as excinfo:
        await adapter.fetch(_source({"subreddit": "saas"}))

    assert str(excinfo.value) == "PROVIDER_RATE_LIMITED: reddit rate limited"
    assert excinfo.value.retry_after_seconds == 120
    await client.aclose()


async def test_reddit_429_without_retry_after_has_none():
    client = _client(lambda request: httpx.Response(429))
    adapter = RedditAdapter(client=client, user_agent="test-agent")

    with pytest.raises(ProviderRateLimited) as excinfo:
        await adapter.fetch(_source({"subreddit": "saas"}))

    assert excinfo.value.retry_after_seconds is None
    await client.aclose()


@pytest.mark.parametrize("status", [401, 403])
async def test_reddit_auth_errors(status):
    client = _client(lambda request: httpx.Response(status))
    adapter = RedditAdapter(client=client, user_agent="test-agent")

    with pytest.raises(ProviderAuthError):
        await adapter.fetch(_source({"subreddit": "saas"}))

    await client.aclose()


@pytest.mark.parametrize("status", [500, 503])
async def test_reddit_server_errors_raise_unavailable(status):
    client = _client(lambda request: httpx.Response(status))
    adapter = RedditAdapter(client=client, user_agent="test-agent")

    with pytest.raises(ProviderUnavailable):
        await adapter.fetch(_source({"subreddit": "saas"}))

    await client.aclose()


async def test_reddit_other_non_200_raises_unavailable():
    client = _client(lambda request: httpx.Response(418))
    adapter = RedditAdapter(client=client, user_agent="test-agent")

    with pytest.raises(ProviderUnavailable):
        await adapter.fetch(_source({"subreddit": "saas"}))

    await client.aclose()


async def test_reddit_404_names_subreddit():
    client = _client(lambda request: httpx.Response(404))
    adapter = RedditAdapter(client=client, user_agent="test-agent")

    with pytest.raises(ProviderNotConfigured) as excinfo:
        await adapter.fetch(_source({"subreddit": "doesnotexist"}))

    assert str(excinfo.value) == (
        "PROVIDER_NOT_CONFIGURED: reddit subreddit r/doesnotexist may not exist"
    )
    await client.aclose()


async def test_reddit_timeout_raises_unavailable():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    client = _client(handler)
    adapter = RedditAdapter(client=client, user_agent="test-agent")

    with pytest.raises(ProviderUnavailable):
        await adapter.fetch(_source({"subreddit": "saas"}))

    await client.aclose()


async def test_reddit_invalid_json_raises_bad_output():
    client = _client(
        lambda request: httpx.Response(
            200,
            content=b"not-json",
            headers={"content-type": "application/json"},
        )
    )
    adapter = RedditAdapter(client=client, user_agent="test-agent")

    with pytest.raises(ProviderBadOutput):
        await adapter.fetch(_source({"subreddit": "saas"}))

    await client.aclose()


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {},
        {"data": None},
        {"data": {}},
        {"data": {"children": "nope"}},
        {"data": {"children": {}}},
    ],
)
async def test_reddit_bad_payload_shape_raises_bad_output(payload):
    client = _client(_ok_handler(payload))
    adapter = RedditAdapter(client=client, user_agent="test-agent")

    with pytest.raises(ProviderBadOutput):
        await adapter.fetch(_source({"subreddit": "saas"}))

    await client.aclose()


# ---------------------------------------------------------------------------
# Health, ownership, and construction from config
# ---------------------------------------------------------------------------


async def test_reddit_health_is_ready_without_network():
    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        raise AssertionError("health must not make a network call")

    client = _client(handler)
    adapter = RedditAdapter(client=client, user_agent="test-agent")

    health = await adapter.health()

    assert health == AdapterHealth(name="reddit", status="ready")
    await client.aclose()


async def test_reddit_aclose_leaves_supplied_client_open():
    client = httpx.AsyncClient()
    adapter = RedditAdapter(client=client, user_agent="test-agent")

    await adapter.aclose()

    assert client.is_closed is False
    await client.aclose()


async def test_reddit_from_config_closes_own_client():
    config = ProviderConfig(
        tenant_id=uuid4(),
        capability="social_source",
        provider="reddit",
        config={"user_agent": "test-agent"},
    )
    adapter = RedditAdapter.from_config(config, EnvSecretResolver())

    assert adapter._user_agent == "test-agent"
    await adapter.aclose()

    assert adapter._client.is_closed is True


def test_reddit_from_config_requires_user_agent():
    config = ProviderConfig(
        tenant_id=uuid4(),
        capability="social_source",
        provider="reddit",
        config={},
    )

    with pytest.raises(ProviderNotConfigured) as excinfo:
        RedditAdapter.from_config(config, EnvSecretResolver())

    assert str(excinfo.value) == ("PROVIDER_NOT_CONFIGURED: reddit user_agent")


async def test_reddit_from_config_reads_user_agent_secret_ref(monkeypatch):
    monkeypatch.setenv("GROWTH_REDDIT_USER_AGENT", "secret-agent")
    config = ProviderConfig(
        tenant_id=uuid4(),
        capability="social_source",
        provider="reddit",
        config={"base_url": "https://reddit.example"},
        secret_ref="GROWTH_REDDIT_USER_AGENT",
    )

    adapter = RedditAdapter.from_config(config, EnvSecretResolver())

    assert adapter._user_agent == "secret-agent"
    assert adapter._base_url == "https://reddit.example"
    await adapter.aclose()


# ---------------------------------------------------------------------------
# Registry integration
# ---------------------------------------------------------------------------


def test_registry_resolves_reddit_adapter_from_config_user_agent():
    config = ProviderConfig(
        tenant_id=uuid4(),
        capability="social_source",
        provider="reddit",
        priority=10,
        enabled=True,
        config={"user_agent": "test-agent"},
        secret_ref=None,
    )

    adapter = AdapterRegistry([config], EnvSecretResolver()).source("reddit")

    assert isinstance(adapter, RedditAdapter)
    import asyncio

    asyncio.run(adapter.aclose())
