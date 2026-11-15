"""Tests for the adapter registry, protocols, and secret resolution."""

from __future__ import annotations

import pytest

from growth_core.adapters.base import ProviderNotConfigured
from growth_core.adapters.feishu import FeishuNotifier
from growth_core.adapters.registry import (
    AdapterRegistry,
    EnvSecretResolver,
    register_adapter,
)
from growth_core.schemas import ProviderConfig

TENANT_ID = "00000000-0000-0000-0000-000000000001"


def _config(
    capability: str,
    provider: str,
    *,
    priority: int = 10,
    enabled: bool = True,
    config: dict | None = None,
    secret_ref: str | None = None,
) -> ProviderConfig:
    return ProviderConfig(
        tenant_id=TENANT_ID,
        capability=capability,
        provider=provider,
        priority=priority,
        enabled=enabled,
        config=config or {},
        secret_ref=secret_ref,
    )


class DummySource:
    name = "dummy"

    def __init__(self, config, secrets):
        self.config = config
        self.secrets = secrets

    async def fetch(self, source):
        return []

    async def health(self):
        return None


class DummyNotifier:
    name = "dummy"

    def __init__(self, config, secrets):
        self.config = config
        self.secrets = secrets

    async def send_card(self, chat_id, card):
        return "fake-message-id"

    async def health(self):
        return None


class DummyLLM:
    name = "dummy"

    def __init__(self, config, secrets):
        self.config = config
        self.secrets = secrets

    async def complete_json(self, *, system, user, schema, model=None):
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Source resolution
# ---------------------------------------------------------------------------


def test_registry_resolves_configured_source(monkeypatch):
    register_adapter("social_source", "dummy")(DummySource)
    config = ProviderConfig(
        tenant_id="00000000-0000-0000-0000-000000000001",
        capability="social_source", provider="dummy",
        priority=10, enabled=True, config={}, secret_ref=None,
    )
    registry = AdapterRegistry([config], EnvSecretResolver())
    adapter = registry.source("dummy")
    assert adapter.name == "dummy"


def test_registry_missing_provider_raises():
    registry = AdapterRegistry([], EnvSecretResolver())
    with pytest.raises(ProviderNotConfigured):
        registry.source("reddit")


def test_registry_ignores_disabled_source_config():
    register_adapter("social_source", "disabled_source")(DummySource)
    config = _config("social_source", "disabled_source", enabled=False)
    registry = AdapterRegistry([config], EnvSecretResolver())
    with pytest.raises(ProviderNotConfigured) as excinfo:
        registry.source("disabled_source")
    assert str(excinfo.value) == (
        "PROVIDER_NOT_CONFIGURED: social_source/disabled_source"
    )


def test_registry_missing_factory_raises():
    config = _config("social_source", "unregistered_provider")
    registry = AdapterRegistry([config], EnvSecretResolver())
    with pytest.raises(ProviderNotConfigured) as excinfo:
        registry.source("unregistered_provider")
    assert str(excinfo.value) == (
        "PROVIDER_NOT_CONFIGURED: social_source/unregistered_provider"
    )


def test_register_adapter_returns_decorated_object_unchanged():
    class Sentinel:
        pass

    returned = register_adapter("social_source", "sentinel")(Sentinel)
    assert returned is Sentinel


def test_registry_passes_config_and_secrets_to_factory():
    register_adapter("social_source", "passed_config")(DummySource)
    config = _config("social_source", "passed_config")
    secrets = EnvSecretResolver()
    adapter = AdapterRegistry([config], secrets).source("passed_config")
    assert adapter.config is config
    assert adapter.secrets is secrets


# ---------------------------------------------------------------------------
# Notifier / LLM selection
# ---------------------------------------------------------------------------


def test_registry_notifier_picks_lowest_priority():
    register_adapter("notifier", "alpha")(DummyNotifier)
    register_adapter("notifier", "beta")(DummyNotifier)
    configs = [
        _config("notifier", "alpha", priority=5),
        _config("notifier", "beta", priority=1),
    ]
    chosen = AdapterRegistry(configs, EnvSecretResolver()).notifier()
    assert chosen.config.provider == "beta"


def test_registry_notifier_ties_break_on_provider_name():
    register_adapter("notifier", "zeta")(DummyNotifier)
    register_adapter("notifier", "alpha")(DummyNotifier)
    configs = [
        _config("notifier", "zeta", priority=10),
        _config("notifier", "alpha", priority=10),
    ]
    chosen = AdapterRegistry(configs, EnvSecretResolver()).notifier()
    assert chosen.config.provider == "alpha"


def test_registry_notifier_without_config_names_capability_only():
    registry = AdapterRegistry([], EnvSecretResolver())
    with pytest.raises(ProviderNotConfigured) as excinfo:
        registry.notifier()
    assert str(excinfo.value) == "PROVIDER_NOT_CONFIGURED: notifier"


def test_registry_notifier_without_factory_names_capability_and_provider():
    config = _config("notifier", "no_factory_notifier")
    registry = AdapterRegistry([config], EnvSecretResolver())
    with pytest.raises(ProviderNotConfigured) as excinfo:
        registry.notifier()
    assert str(excinfo.value) == (
        "PROVIDER_NOT_CONFIGURED: notifier/no_factory_notifier"
    )


def test_registry_llm_picks_lowest_priority():
    register_adapter("llm", "big")(DummyLLM)
    register_adapter("llm", "small")(DummyLLM)
    configs = [
        _config("llm", "big", priority=1),
        _config("llm", "small", priority=2),
    ]
    chosen = AdapterRegistry(configs, EnvSecretResolver()).llm()
    assert chosen.config.provider == "big"


def test_registry_llm_without_config_names_capability_only():
    registry = AdapterRegistry([], EnvSecretResolver())
    with pytest.raises(ProviderNotConfigured) as excinfo:
        registry.llm()
    assert str(excinfo.value) == "PROVIDER_NOT_CONFIGURED: llm"


def test_registry_llm_ignores_disabled_config():
    register_adapter("llm", "off")(DummyLLM)
    config = _config("llm", "off", enabled=False)
    registry = AdapterRegistry([config], EnvSecretResolver())
    with pytest.raises(ProviderNotConfigured):
        registry.llm()


async def test_registry_resolves_feishu_notifier(monkeypatch):
    monkeypatch.setenv("GROWTH_FEISHU_APP_ID", "app-id")
    monkeypatch.setenv("GROWTH_FEISHU_APP_SECRET", "app-secret")
    config = _config(
        "notifier",
        "feishu",
        secret_ref="GROWTH_FEISHU_APP_SECRET",
    )
    notifier = AdapterRegistry([config], EnvSecretResolver()).notifier()
    try:
        assert isinstance(notifier, FeishuNotifier)
    finally:
        await notifier.aclose()


# ---------------------------------------------------------------------------
# Secret resolution
# ---------------------------------------------------------------------------


def test_env_secret_resolver_reads_environment(monkeypatch):
    monkeypatch.setenv("GROWTH_TEST_TOKEN", "secret-value")
    assert EnvSecretResolver().get("GROWTH_TEST_TOKEN") == "secret-value"


def test_env_secret_resolver_missing_env_names_variable_only(monkeypatch):
    monkeypatch.delenv("GROWTH_TEST_MISSING_TOKEN", raising=False)
    with pytest.raises(ProviderNotConfigured) as excinfo:
        EnvSecretResolver().get("GROWTH_TEST_MISSING_TOKEN")
    assert str(excinfo.value) == (
        "SECRET_NOT_CONFIGURED: GROWTH_TEST_MISSING_TOKEN"
    )


def test_env_secret_resolver_empty_ref_raises():
    with pytest.raises(ProviderNotConfigured) as excinfo:
        EnvSecretResolver().get("")
    assert str(excinfo.value) == "SECRET_REF_MISSING"

    with pytest.raises(ProviderNotConfigured) as excinfo:
        EnvSecretResolver().get(None)
    assert str(excinfo.value) == "SECRET_REF_MISSING"


# ---------------------------------------------------------------------------
# Feishu from_config
# ---------------------------------------------------------------------------


def test_feishu_from_config_uses_env_and_secret_resolver(monkeypatch):
    monkeypatch.setenv("GROWTH_FEISHU_APP_ID", "app-id")
    monkeypatch.setenv("GROWTH_FEISHU_APP_SECRET", "app-secret")
    config = _config(
        "notifier",
        "feishu",
        config={"base_url": "https://feishu.example"},
        secret_ref="GROWTH_FEISHU_APP_SECRET",
    )
    notifier = FeishuNotifier.from_config(config, EnvSecretResolver())
    assert notifier._app_id == "app-id"
    assert notifier._app_secret == "app-secret"
    assert notifier._base_url == "https://feishu.example"


def test_feishu_from_config_missing_app_id_names_env_var(monkeypatch):
    monkeypatch.delenv("GROWTH_FEISHU_APP_ID", raising=False)
    config = _config("notifier", "feishu", config={})
    with pytest.raises(ProviderNotConfigured) as excinfo:
        FeishuNotifier.from_config(config, EnvSecretResolver())
    assert str(excinfo.value) == (
        "SECRET_NOT_CONFIGURED: GROWTH_FEISHU_APP_ID"
    )


def test_feishu_from_config_honours_custom_app_id_env(monkeypatch):
    monkeypatch.setenv("CUSTOM_FEISHU_APP_ID", "app-id")
    monkeypatch.setenv("CUSTOM_FEISHU_SECRET", "app-secret")
    config = _config(
        "notifier",
        "feishu",
        config={"app_id_env": "CUSTOM_FEISHU_APP_ID"},
        secret_ref="CUSTOM_FEISHU_SECRET",
    )
    notifier = FeishuNotifier.from_config(config, EnvSecretResolver())
    assert notifier._app_id == "app-id"

    monkeypatch.delenv("CUSTOM_FEISHU_APP_ID")
    with pytest.raises(ProviderNotConfigured) as excinfo:
        FeishuNotifier.from_config(config, EnvSecretResolver())
    assert str(excinfo.value) == "SECRET_NOT_CONFIGURED: CUSTOM_FEISHU_APP_ID"


