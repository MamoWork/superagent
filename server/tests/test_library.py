from __future__ import annotations

from fastapi.testclient import TestClient

from app.config import Settings
from app.db import utcnow
from app.main import create_app
from app.providers.base import SourceProvider
from app.providers.registry import ProviderRegistry
from app.schemas import (
    Citation,
    DimensionScore,
    NextAction,
    OpportunityAnalysis,
    ProviderHealth,
    ProviderInfo,
    SearchQuery,
    Signal,
)


class FakeProvider(SourceProvider):
    def __init__(self) -> None:
        self.info = ProviderInfo(
            id="fake",
            name="Fake",
            group="test",
            capabilities=["search"],
        )

    async def health(self) -> ProviderHealth:
        return ProviderHealth(id="fake", status="ready")

    async def search(self, query: SearchQuery) -> list[Signal]:
        return [
            Signal(
                id="sig-1",
                provider_id="fake",
                source_url="https://example.com/1",
                title="Manual spreadsheet pain",
                quote="I track everything in a spreadsheet.",
            )
        ]


def _app(tmp_path):
    app = create_app(
        settings=Settings(db_path=tmp_path / "test.db"),
        registry=ProviderRegistry([FakeProvider()]),
    )
    return app, TestClient(app)


def _create_run(client: TestClient) -> dict:
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
    return response.json()


def _analysis(run_id: str) -> OpportunityAnalysis:
    return OpportunityAnalysis(
        run_id=run_id,
        domain_pack="crossborder",
        verdict="verify",
        score=72,
        one_liner="Pet fountain replacement filters",
        thesis="Owners complain about cleaning and filter cost.",
        target_customer="US pet owners with a fountain",
        willingness_to_pay="Moderate; replacement parts already sell",
        dimension_scores=[
            DimensionScore(
                dimension_id="demand",
                name="Demand",
                weight=0.4,
                score=8,
                weighted_points=32,
                rationale="Repeated complaints",
                citations=[
                    Citation(
                        signal_id="sig-1",
                        source_url="https://example.com/1",
                        quote="I track everything in a spreadsheet.",
                    )
                ],
            )
        ],
        next_actions=[NextAction(action="Interview five owners", due_in_days=7)],
        risks=["Seasonal demand"],
        citations=[
            Citation(
                signal_id="sig-1",
                source_url="https://example.com/1",
                quote="I track everything in a spreadsheet.",
            )
        ],
        model="test-model",
        created_at=utcnow(),
    )


def test_save_requires_analysis(tmp_path) -> None:
    _, client = _app(tmp_path)
    run = _create_run(client)
    response = client.post("/api/v1/library", json={"run_id": run["id"]})
    assert response.status_code == 409


def test_save_unknown_run_is_404(tmp_path) -> None:
    _, client = _app(tmp_path)
    response = client.post("/api/v1/library", json={"run_id": "run_missing"})
    assert response.status_code == 404


def test_save_update_and_delete_saved_opportunity(tmp_path) -> None:
    app, client = _app(tmp_path)
    run = _create_run(client)
    app.state.db.save_analysis(run["id"], _analysis(run["id"]))

    saved = client.post("/api/v1/library", json={"run_id": run["id"]})
    assert saved.status_code == 201
    item = saved.json()
    assert item["run_id"] == run["id"]
    assert item["stage"] == "saved"
    assert item["title"] == "Pet fountain replacement filters"
    assert item["direction"] == "Amazon pet fountain niche"
    assert item["citations"][0]["source_url"] == "https://example.com/1"

    listed = client.get("/api/v1/library").json()["opportunities"]
    assert len(listed) == 1
    assert listed[0]["run_id"] == run["id"]

    updated = client.patch(
        f"/api/v1/library/{run['id']}",
        json={"stage": "contacted", "notes": "DM sent manually"},
    )
    assert updated.status_code == 200
    assert updated.json()["stage"] == "contacted"
    assert updated.json()["notes"] == "DM sent manually"
    assert updated.json()["created_at"] == item["created_at"]

    fetched = client.get(f"/api/v1/library/{run['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["stage"] == "contacted"

    deleted = client.delete(f"/api/v1/library/{run['id']}")
    assert deleted.status_code == 204
    assert client.get("/api/v1/library").json()["opportunities"] == []


def test_saving_again_updates_snapshot_and_preserves_created_at(tmp_path) -> None:
    app, client = _app(tmp_path)
    run = _create_run(client)
    app.state.db.save_analysis(run["id"], _analysis(run["id"]))

    first = client.post("/api/v1/library", json={"run_id": run["id"]}).json()
    second = client.post(
        "/api/v1/library",
        json={"run_id": run["id"], "stage": "validating", "notes": "checking"},
    ).json()
    assert second["created_at"] == first["created_at"]
    assert second["stage"] == "validating"
    assert second["notes"] == "checking"


def test_invalid_stage_is_rejected(tmp_path) -> None:
    app, client = _app(tmp_path)
    run = _create_run(client)
    app.state.db.save_analysis(run["id"], _analysis(run["id"]))
    response = client.post(
        "/api/v1/library",
        json={"run_id": run["id"], "stage": "not-a-stage"},
    )
    assert response.status_code == 422
