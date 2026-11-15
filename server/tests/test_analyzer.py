from __future__ import annotations

import asyncio

from fastapi.testclient import TestClient

from app.config import Settings
from app.db import Database
from app.main import create_app
from app.providers.base import SourceProvider
from app.providers.registry import ProviderRegistry
from app.schemas import (
    AnalysisDraft,
    CitationDraft,
    DimensionDraft,
    ProviderHealth,
    ProviderInfo,
    Run,
    SearchQuery,
    Signal,
)
from app.services.analyzer import ai_status, analyze_run, build_engine


class FakeEngine:
    name = "fake:test-model"

    def __init__(self, draft: AnalysisDraft) -> None:
        self._draft = draft

    async def draft(self, run: Run, pack) -> AnalysisDraft:
        return self._draft


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
                title="Manual comparison pain",
                quote="I compare 20 listings by hand in a spreadsheet.",
                author_public="u/seller",
            )
        ]


def _draft(score: int = 9, with_citation: bool = True) -> AnalysisDraft:
    return AnalysisDraft(
        one_liner="细分宠物饮水机值得验证",
        thesis="卖家反复提到手工比价和隐藏成本。",
        target_customer="刚起步的 Amazon 单品类卖家",
        willingness_to_pay="有付费工具预算，但未验证具体金额。",
        dimensions=[
            DimensionDraft(
                dimension_id="demand",
                score=score,
                rationale="多条帖子描述重复的手工流程。",
                citations=[
                    CitationDraft(signal_id="sig-1", quote="compare 20 listings")
                ]
                if with_citation
                else [],
            ),
            DimensionDraft(
                dimension_id="competition",
                score=7,
                rationale="有替代工具，但未覆盖跨境利润与供应。",
                citations=[],
            ),
            DimensionDraft(
                dimension_id="margin", score=8, rationale="卖家关注隐藏成本。"
            ),
            DimensionDraft(
                dimension_id="sourcing", score=7, rationale="供应商核验是高频问题。"
            ),
            DimensionDraft(
                dimension_id="compliance", score=6, rationale="未看到系统性合规证据。"
            ),
            DimensionDraft(
                dimension_id="confidence",
                score=8,
                rationale="有原文链接和作者信息。",
                citations=(
                    [
                        CitationDraft(signal_id="sig-1", quote="spreadsheet"),
                        CitationDraft(signal_id="sig-fake", quote="编造的引用"),
                    ]
                    if with_citation
                    else []
                ),
            ),
        ],
        next_actions=["访谈 3 个卖家", "核对 10 个竞品价格"],
        risks=["样本只来自 Reddit"],
        missing_information=["缺少真实成交数据"],
    )


def _make_run(tmp_path) -> tuple[Database, Run]:
    db = Database(tmp_path / "test.db")
    db.init()
    run_id = "run_test"
    db.create_run(
        {
            "id": run_id,
            "workspace_id": "test",
            "domain_pack": "crossborder",
            "direction": "Amazon 宠物饮水机",
            "keywords": ["pet fountain"],
            "provider_ids": ["fake"],
            "status": "completed",
            "stats": {"time_range_days": 90},
            "created_at": "2026-01-01T00:00:00+00:00",
        }
    )
    db.add_signals(
        run_id,
        [
            Signal(
                id="sig-1",
                provider_id="fake",
                source_url="https://example.com/1",
                title="Manual comparison pain",
                quote="I compare 20 listings by hand in a spreadsheet.",
                author_public="u/seller",
            )
        ],
    )
    data = db.get_run(run_id)
    assert data is not None
    return db, Run(**data, signals=db.get_signals(run_id))


def test_analysis_scores_and_resolves_citations(tmp_path) -> None:
    db, run = _make_run(tmp_path)
    analysis = asyncio.run(
        analyze_run(db, run, FakeEngine(_draft()), timeout=5)
    )

    assert analysis.verdict == "build"
    assert analysis.score == 77
    assert len(analysis.dimension_scores) == 6
    assert analysis.citations[0].source_url == "https://example.com/1"
    assert all(c.signal_id != "sig-fake" for c in analysis.citations)
    assert db.get_analysis(run.id) is not None


def test_no_citation_never_builds(tmp_path) -> None:
    db, run = _make_run(tmp_path)
    analysis = asyncio.run(
        analyze_run(db, run, FakeEngine(_draft(with_citation=False)), timeout=5)
    )

    assert analysis.verdict == "verify"
    assert any("没有可核对" in item for item in analysis.missing_information)


def test_ai_status_and_engine_are_opt_in(tmp_path) -> None:
    settings = Settings(db_path=tmp_path / "test.db", ai_model=None)
    assert build_engine(settings) is None
    status = ai_status(settings)
    assert status.configured is False


def test_analysis_api(tmp_path) -> None:
    db, run = _make_run(tmp_path)
    app = create_app(
        settings=Settings(db_path=db.path, ai_model=None),
        registry=ProviderRegistry([FakeProvider()]),
        analysis_engine=FakeEngine(_draft()),
    )
    client = TestClient(app)

    before = client.get(f"/api/v1/runs/{run.id}")
    assert before.status_code == 200
    assert before.json()["has_analysis"] is False

    response = client.post(f"/api/v1/runs/{run.id}/analyze", json={})
    assert response.status_code == 200
    payload = response.json()
    assert payload["verdict"] == "build"
    assert payload["citations"][0]["source_url"] == "https://example.com/1"

    saved = client.get(f"/api/v1/runs/{run.id}/analysis")
    assert saved.status_code == 200
    assert saved.json()["score"] == 77

    after = client.get(f"/api/v1/runs/{run.id}")
    assert after.json()["has_analysis"] is True
    listed = client.get("/api/v1/runs").json()["runs"]
    assert listed[0]["has_analysis"] is True

    markdown = client.get(f"/api/v1/runs/{run.id}/analysis.md")
    assert markdown.status_code == 200
    assert "https://example.com/1" in markdown.text
    assert "建议投入" in markdown.text


def test_analysis_api_requires_engine(tmp_path) -> None:
    db, run = _make_run(tmp_path)
    app = create_app(
        settings=Settings(db_path=db.path, ai_model=None),
        registry=ProviderRegistry([FakeProvider()]),
    )
    client = TestClient(app)

    response = client.post(f"/api/v1/runs/{run.id}/analyze", json={})
    assert response.status_code == 400
