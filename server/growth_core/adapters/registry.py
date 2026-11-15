"""Adapter registry and environment-backed secret resolution.

Adapters register a factory under a ``(capability, provider)`` key with
:func:`register_adapter`. :class:`AdapterRegistry` then resolves the eligible
:class:`~growth_core.schemas.ProviderConfig` rows it was constructed with and
calls the matching factory with ``(config, secrets)``.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Sequence
from typing import Any, TypeVar

from growth_core.adapters.base import (
    ProviderNotConfigured,
    SecretResolver,
)
from growth_core.schemas import ProviderConfig

__all__ = [
    "AdapterFactory",
    "AdapterRegistry",
    "EnvSecretResolver",
    "register_adapter",
]

AdapterFactory = Callable[[ProviderConfig, SecretResolver], Any]

_F = TypeVar("_F", bound=Callable[..., Any])

_FACTORIES: dict[tuple[str, str], AdapterFactory] = {}


class EnvSecretResolver:
    """Resolve secret references as environment variable names.

    Error messages name the missing variable (or report that no reference was
    supplied) and never contain the resolved value.
    """

    def get(self, ref: str | None) -> str:
        if not ref:
            raise ProviderNotConfigured("SECRET_REF_MISSING")
        value = os.environ.get(ref)
        if value is None:
            raise ProviderNotConfigured(f"SECRET_NOT_CONFIGURED: {ref}")
        return value


def register_adapter(capability: str, provider: str) -> Callable[[_F], _F]:
    """Register ``factory`` under ``(capability, provider)``.

    The decorated object is returned unchanged. A later registration for the
    same key replaces the earlier factory.
    """

    def _register(factory: _F) -> _F:
        _FACTORIES[(capability, provider)] = factory  # type: ignore[assignment]
        return factory

    return _register


class AdapterRegistry:
    """Resolve adapters from the provider configs supplied at construction."""

    def __init__(
        self,
        configs: Sequence[ProviderConfig],
        secrets: SecretResolver,
    ) -> None:
        self._secrets = secrets
        self._configs: dict[tuple[str, str], ProviderConfig] = {
            (config.capability, config.provider): config
            for config in configs
            if config.enabled
        }

    def source(self, provider: str) -> Any:
        """Resolve the social source adapter named ``provider``."""
        config = self._configs.get(("social_source", provider))
        if config is None:
            raise ProviderNotConfigured(
                f"PROVIDER_NOT_CONFIGURED: social_source/{provider}"
            )
        return self._build("social_source", config)

    def notifier(self) -> Any:
        """Resolve the preferred notifier adapter."""
        return self._build("notifier", self._preferred("notifier"))

    def llm(self) -> Any:
        """Resolve the preferred LLM adapter."""
        return self._build("llm", self._preferred("llm"))

    def _preferred(self, capability: str) -> ProviderConfig:
        eligible = [
            config
            for config in self._configs.values()
            if config.capability == capability
        ]
        if not eligible:
            raise ProviderNotConfigured(
                f"PROVIDER_NOT_CONFIGURED: {capability}"
            )
        return min(eligible, key=lambda config: (config.priority, config.provider))

    def _build(self, capability: str, config: ProviderConfig) -> Any:
        factory = _FACTORIES.get((capability, config.provider))
        if factory is None:
            raise ProviderNotConfigured(
                f"PROVIDER_NOT_CONFIGURED: {capability}/{config.provider}"
            )
        return factory(config, self._secrets)
