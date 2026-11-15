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

    async def health(self) -> ProviderHealth:
        return ProviderHealth(id="fake", status="ready")

    async def search(self, query: SearchQuery) -> list[Signal]:
        return []


def _make_dist(tmp_path):
    dist = tmp_path / "dist"
    assets = dist / "assets"
    assets.mkdir(parents=True)
    (dist / "index.html").write_text(
        "<!doctype html><html><head><title>Scout</title></head>"
        '<body><div id="root"></div></body></html>',
        encoding="utf-8",
    )
    (assets / "app-abc123.js").write_text("console.log('scout');", encoding="utf-8")
    (dist / "favicon.svg").write_text("<svg></svg>", encoding="utf-8")
    return dist


def _client(tmp_path, dist=None) -> TestClient:
    app = create_app(
        settings=Settings(
            db_path=tmp_path / "test.db",
            web_dist_dir=dist,
        ),
        registry=ProviderRegistry([FakeProvider()]),
    )
    return TestClient(app)


def test_serves_injected_index_and_deep_links(tmp_path) -> None:
    dist = _make_dist(tmp_path)
    client = _client(tmp_path, dist)
    client.app.state.desktop_token = "test-token"

    for path in ("/", "/index.html", "/history", "/results/run_abc", "/settings"):
        response = client.get(path)
        assert response.status_code == 200, path
        assert "text/html" in response.headers["content-type"]
        assert 'OPPORTUNITY_API_BASE="/api/v1"' in response.text
        assert 'OPPORTUNITY_DESKTOP_TOKEN="test-token"' in response.text
        assert response.headers["cache-control"] == "no-store"


def test_serves_hashed_assets_with_immutable_cache(tmp_path) -> None:
    dist = _make_dist(tmp_path)
    client = _client(tmp_path, dist)

    response = client.get("/assets/app-abc123.js")
    assert response.status_code == 200
    assert response.text == "console.log('scout');"
    assert "immutable" in response.headers["cache-control"]

    missing = client.get("/assets/missing.js")
    assert missing.status_code == 404


def test_serves_other_dist_files(tmp_path) -> None:
    dist = _make_dist(tmp_path)
    client = _client(tmp_path, dist)
    response = client.get("/favicon.svg")
    assert response.status_code == 200
    assert "image/svg+xml" in response.headers["content-type"]


def test_unknown_api_path_is_json_404(tmp_path) -> None:
    dist = _make_dist(tmp_path)
    client = _client(tmp_path, dist)
    response = client.get("/api/v1/does-not-exist")
    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/json")
    assert response.json()["detail"] == "Not Found"


def test_missing_file_is_not_replaced_by_index(tmp_path) -> None:
    dist = _make_dist(tmp_path)
    client = _client(tmp_path, dist)
    response = client.get("/missing.js")
    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/json")


def test_missing_dist_shows_build_instructions(tmp_path) -> None:
    client = _client(tmp_path, tmp_path / "missing")
    response = client.get("/")
    assert response.status_code == 404
    assert "前端尚未构建" in response.text
    info = client.get("/api/v1/app/info").json()
    assert info["ui_available"] is False


def test_api_docs_still_work(tmp_path) -> None:
    dist = _make_dist(tmp_path)
    client = _client(tmp_path, dist)
    assert client.get("/docs").status_code == 200
    assert client.get("/openapi.json").status_code == 200


def test_no_token_is_injected_without_desktop_mode(tmp_path) -> None:
    dist = _make_dist(tmp_path)
    client = _client(tmp_path, dist)
    response = client.get("/")
    assert "OPPORTUNITY_DESKTOP_TOKEN" not in response.text
