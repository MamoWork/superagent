from __future__ import annotations

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.providers.base import SourceProvider
from app.providers.registry import ProviderRegistry
from app.schemas import ProviderHealth, ProviderInfo, SearchQuery, Signal


class FakeProvider(SourceProvider):
    def __init__(self) -> None:
        self.info = ProviderInfo(id="fake", name="Fake", group="test")

    async def health(self) -> ProviderHealth:
        return ProviderHealth(id="fake", status="ready")

    async def search(self, query: SearchQuery) -> list[Signal]:
        return [
            Signal(
                id="sig-1",
                provider_id="fake",
                source_url="https://example.com/1",
                title="Scheduled signal",
                quote="A real complaint.",
            )
        ]


def _client(tmp_path) -> TestClient:
    app = create_app(
        settings=Settings(
            db_path=tmp_path / "test.db",
            scheduler_enabled=False,
        ),
        registry=ProviderRegistry([FakeProvider()]),
    )
    return TestClient(app)


def _payload(**overrides):
    data = {
        "domain_pack": "general",
        "direction": "Scheduled research",
        "keywords": ["manual"],
        "provider_ids": ["fake"],
        "limit_per_provider": 5,
        "cron": "0 9 * * *",
    }
    data.update(overrides)
    return data


def test_schedule_crud(tmp_path) -> None:
    client = _client(tmp_path)
    created = client.post("/api/v1/schedules", json=_payload())
    assert created.status_code == 201
    schedule = created.json()
    assert schedule["enabled"] is True
    assert schedule["next_run_at"] is not None

    listed = client.get("/api/v1/schedules").json()["schedules"]
    assert len(listed) == 1
    assert listed[0]["id"] == schedule["id"]

    updated = client.patch(
        f"/api/v1/schedules/{schedule['id']}",
        json={"enabled": False, "cron": "30 8 * * 1-5"},
    )
    assert updated.status_code == 200
    assert updated.json()["enabled"] is False
    assert updated.json()["next_run_at"] is None

    deleted = client.delete(f"/api/v1/schedules/{schedule['id']}")
    assert deleted.status_code == 204
    assert client.get("/api/v1/schedules").json()["schedules"] == []


def test_invalid_cron_is_rejected(tmp_path) -> None:
    client = _client(tmp_path)
    response = client.post("/api/v1/schedules", json=_payload(cron="not a cron"))
    assert response.status_code == 400


def test_run_now_creates_a_run(tmp_path) -> None:
    client = _client(tmp_path)
    schedule = client.post("/api/v1/schedules", json=_payload()).json()

    response = client.post(f"/api/v1/schedules/{schedule['id']}/run")
    assert response.status_code == 200
    run = response.json()
    assert run["status"] == "completed"
    assert len(run["signals"]) == 1

    refreshed = client.get(f"/api/v1/schedules/{schedule['id']}").json()
    assert refreshed["last_run_id"] == run["id"]
    assert refreshed["last_run_at"] is not None


def test_disabled_schedule_cannot_run_now(tmp_path) -> None:
    client = _client(tmp_path)
    schedule = client.post(
        "/api/v1/schedules", json=_payload(enabled=False)
    ).json()
    response = client.post(f"/api/v1/schedules/{schedule['id']}/run")
    assert response.status_code == 400
