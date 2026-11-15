from __future__ import annotations

import asyncio
import json

import pytest

from app.providers.agent_reach import AgentReachProvider
from app.providers.base import ProviderError
from app.schemas import SearchQuery


def _script(tmp_path, payload: dict) -> str:
    path = tmp_path / "fake-agent-reach"
    path.write_text(
        "#!/bin/sh\ncat <<'JSON'\n"
        + json.dumps(payload, ensure_ascii=False)
        + "\nJSON\n",
        encoding="utf-8",
    )
    path.chmod(0o755)
    return str(path)


def test_normalizes_items(tmp_path) -> None:
    bin_path = _script(
        tmp_path,
        {
            "ok": True,
            "items": [
                {
                    "title": "A real complaint",
                    "url": "https://example.com/post/1",
                    "author": "u/example",
                    "published_at": "2026-01-01T00:00:00Z",
                    "text": "I do this manually in a spreadsheet.",
                    "raw": {"source": "test"},
                }
            ],
            "meta": {},
        },
    )
    provider = AgentReachProvider(
        channel="reddit",
        bin_path=bin_path,
        backend="public-web",
        timeout=5,
    )
    signals = asyncio.run(provider.search(SearchQuery(text="test", limit=1)))

    assert len(signals) == 1
    signal = signals[0]
    assert signal.provider_id == "agent-reach.reddit"
    assert signal.source_url == "https://example.com/post/1"
    assert signal.title == "A real complaint"
    assert signal.author_public == "u/example"
    assert signal.quote == "I do this manually in a spreadsheet."
    assert len(signal.id) == 24


def test_maps_platform_error(tmp_path) -> None:
    bin_path = _script(
        tmp_path,
        {
            "ok": False,
            "error": {
                "code": "RATE_LIMITED",
                "message": "slow down",
                "hint": "wait",
                "retry_after_seconds": 30,
            },
            "items": [],
        },
    )
    provider = AgentReachProvider(channel="reddit", bin_path=bin_path, timeout=5)

    with pytest.raises(ProviderError) as exc:
        asyncio.run(provider.search(SearchQuery(text="test", limit=1)))

    assert exc.value.code == "PROVIDER_RATE_LIMITED"
    assert exc.value.retry_after_seconds == 30
    assert exc.value.message == "slow down"


def test_missing_binary_is_typed(tmp_path) -> None:
    provider = AgentReachProvider(
        channel="reddit",
        bin_path=str(tmp_path / "does-not-exist"),
        timeout=5,
    )

    with pytest.raises(ProviderError) as exc:
        asyncio.run(provider.search(SearchQuery(text="test", limit=1)))

    assert exc.value.code == "PROVIDER_NOT_CONFIGURED"


def test_health_reports_ready(tmp_path) -> None:
    bin_path = _script(tmp_path, {"ok": True, "items": []})
    provider = AgentReachProvider(channel="reddit", bin_path=bin_path, timeout=5)
    health = asyncio.run(provider.health())
    assert health.status == "ready"
    assert health.detail == bin_path
