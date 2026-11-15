from __future__ import annotations

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.providers.base import SourceProvider
from app.providers.registry import ProviderRegistry
from app.schemas import ProviderHealth, ProviderInfo, SearchQuery, Signal


class FakeProvider(SourceProvider):
    def __init__(self) -> None:
        self.info = ProviderInfo(
            id="fake",
            name="Fake",
            group="test",
            capabilities=["search"],
        )
        self.queries: list[SearchQuery] = []

    async def health(self) -> ProviderHealth:
        return ProviderHealth(id="fake", status="ready")

    async def search(self, query: SearchQuery) -> list[Signal]:
        self.queries.append(query)
        return [
            Signal(
                id="sig-1",
                provider_id="fake",
                source_url="https://example.com/1",
                title="Manual spreadsheet pain",
                quote="I track everything in a spreadsheet and it is time-consuming.",
                author_public="u/example",
            )
        ]


def _client(tmp_path) -> TestClient:
    app = create_app(
        settings=Settings(db_path=tmp_path / "test.db"),
        registry=ProviderRegistry([FakeProvider()]),
    )
    return TestClient(app)


def test_list_providers(tmp_path) -> None:
    client = _client(tmp_path)
    response = client.get("/api/v1/providers")
    assert response.status_code == 200
    assert response.json()["providers"][0]["id"] == "fake"


def test_run_and_brief(tmp_path) -> None:
    client = _client(tmp_path)
    response = client.post(
        "/api/v1/runs",
        json={
            "domain_pack": "crossborder",
            "direction": "Amazon pet fountain niche",
            "keywords": ["stainless steel"],
            "provider_ids": ["fake"],
            "limit_per_provider": 5,
        },
    )
    assert response.status_code == 200
    run = response.json()
    assert run["status"] == "completed"
    assert len(run["signals"]) == 1
    assert run["signals"][0]["source_url"] == "https://example.com/1"

    brief = client.get(f"/api/v1/runs/{run['id']}/brief")
    assert brief.status_code == 200
    assert "Amazon pet fountain niche" in brief.text
    assert "https://example.com/1" in brief.text


def test_manual_signal_can_be_added(tmp_path) -> None:
    client = _client(tmp_path)
    run = client.post(
        "/api/v1/runs",
        json={
            "direction": "test",
            "provider_ids": ["fake"],
        },
    ).json()

    response = client.post(
        f"/api/v1/runs/{run['id']}/signals",
        json={
            "provider_id": "manual",
            "source_url": "https://example.com/manual",
            "title": "Supplier quote",
            "quote": "MOQ 500, sample in 7 days.",
        },
    )
    assert response.status_code == 200

    signals = client.get(f"/api/v1/runs/{run['id']}/signals").json()["signals"]
    assert len(signals) == 2
    assert {item["provider_id"] for item in signals} == {"fake", "manual"}


def test_unknown_provider_is_rejected(tmp_path) -> None:
    client = _client(tmp_path)
    response = client.post(
        "/api/v1/runs",
        json={"direction": "test", "provider_ids": ["missing"]},
    )
    assert response.status_code == 400


def test_domain_packs_are_exposed(tmp_path) -> None:
    client = _client(tmp_path)
    response = client.get("/api/v1/domain-packs")
    assert response.status_code == 200
    packs = {item["id"]: item for item in response.json()["domain_packs"]}
    assert "crossborder" in packs
    assert sum(item["weight"] for item in packs["crossborder"]["scorecard"]) == 1.0


def test_unknown_domain_pack_is_rejected(tmp_path) -> None:
    client = _client(tmp_path)
    response = client.post(
        "/api/v1/runs",
        json={
            "direction": "test",
            "provider_ids": ["fake"],
            "domain_pack": "missing",
        },
    )
    assert response.status_code == 400
