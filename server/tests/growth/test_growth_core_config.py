import pytest

from growth_core.config import GrowthConfigError, GrowthSettings


def test_growth_settings_from_env(monkeypatch):
    monkeypatch.setenv("GROWTH_DATABASE_URL", "postgresql://u:p@localhost/db")
    monkeypatch.setenv("GROWTH_SERVICE_TOKEN", "test-token")
    monkeypatch.setenv("GROWTH_TENANT_ID", "00000000-0000-0000-0000-000000000001")
    monkeypatch.setenv("GROWTH_WORKSPACE_ID", "00000000-0000-0000-0000-000000000002")
    settings = GrowthSettings.from_env()
    assert settings.database_url == "postgresql://u:p@localhost/db"
    assert settings.global_daily_limit == 50
    assert settings.reddit_daily_limit == 5
    assert settings.followup_max_total == 3
    assert settings.followup_min_interval_hours == 24


def test_missing_required_env_raises(monkeypatch):
    monkeypatch.delenv("GROWTH_DATABASE_URL", raising=False)
    with pytest.raises(GrowthConfigError, match="GROWTH_DATABASE_URL"):
        GrowthSettings.from_env()
