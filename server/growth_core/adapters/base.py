"""Shared adapter primitives: health status and the provider error hierarchy.

Every adapter failure is an :class:`AdapterError` (or a subclass). Error
messages are short, human-readable descriptions and must never contain
credentials, tokens, or authorization headers.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "AdapterHealth",
    "AdapterError",
    "ProviderNotConfigured",
    "ProviderAuthError",
    "ProviderRateLimited",
    "ProviderTimeout",
    "ProviderUnavailable",
    "ProviderBadOutput",
]


@dataclass
class AdapterHealth:
    """Result of an adapter health probe.

    ``status`` is a short machine-readable state (for example ``"ready"``,
    ``"degraded"``, or ``"down"``). ``detail`` is an optional non-secret
    explanation suitable for logs and status endpoints.
    """

    name: str
    status: str
    detail: str = ""


class AdapterError(Exception):
    """Base class for adapter failures with a secret-free message."""

    def __init__(self, message: str = "") -> None:
        super().__init__(message)
        self.message = message


class ProviderNotConfigured(AdapterError):
    """The provider is missing configuration or credentials."""


class ProviderAuthError(AdapterError):
    """The provider rejected the supplied credentials or token."""


class ProviderRateLimited(AdapterError):
    """The provider refused the request because of rate limiting."""


class ProviderTimeout(AdapterError):
    """The provider did not answer before the deadline."""


class ProviderUnavailable(AdapterError):
    """The provider failed, returned a server error, or was unreachable."""


class ProviderBadOutput(AdapterError):
    """The provider responded successfully but the payload was unusable."""
