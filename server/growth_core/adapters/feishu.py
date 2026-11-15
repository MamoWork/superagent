"""Feishu (Lark) notifier adapter.

Sends interactive cards to a Feishu chat using a tenant access token. The
token is cached until slightly before Feishu's advertised expiry. This module
never logs or embeds the app secret, the tenant token, or the Authorization
header in an error message.
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Mapping
from typing import Any

import httpx

from growth_core.adapters.base import (
    AdapterHealth,
    ProviderAuthError,
    ProviderBadOutput,
    ProviderNotConfigured,
    ProviderRateLimited,
    ProviderUnavailable,
    SecretResolver,
)
from growth_core.adapters.registry import register_adapter
from growth_core.schemas import ProviderConfig

__all__ = ["FeishuNotifier"]

_TENANT_TOKEN_PATH = "/open-apis/auth/v3/tenant_access_token/internal"
_SEND_MESSAGE_PATH = "/open-apis/im/v1/messages"
_AUTH_ERROR_CODES = (99991663, 99991664)
_RATE_LIMIT_ERROR_CODES = (99991400,)
_AUTH_HTTP_STATUSES = (401, 403)
_TOKEN_EXPIRY_SKEW_SECONDS = 60


def _json_object(
    response: httpx.Response, context: str
) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError as exc:
        raise ProviderBadOutput(
            f"Feishu {context} response was not valid JSON"
        ) from exc
    if not isinstance(payload, dict):
        raise ProviderBadOutput(
            f"Feishu {context} response was not a JSON object"
        )
    return payload


def _body_code(response: httpx.Response) -> Any:
    try:
        payload = response.json()
    except ValueError:
        return None
    if isinstance(payload, dict):
        return payload.get("code")
    return None


def _raise_for_code(code: Any) -> None:
    """Map a Feishu ``code`` field to the provider error hierarchy."""
    if code in _AUTH_ERROR_CODES:
        raise ProviderAuthError("Feishu rejected the app credentials")
    if code in _RATE_LIMIT_ERROR_CODES:
        raise ProviderRateLimited("Feishu rate limited the request")
    raise ProviderUnavailable(f"Feishu API returned error code {code}")


def _raise_for_http_status(response: httpx.Response) -> None:
    """Map an HTTP status to the provider error hierarchy.

    Feishu sometimes reports auth or rate-limit failures with HTTP 400 and a
    corresponding ``code`` in the body, so the body is consulted for 4xx.
    """
    status = response.status_code
    if status in _AUTH_HTTP_STATUSES:
        raise ProviderAuthError(
            f"Feishu rejected the credentials (HTTP {status})"
        )
    if status == 429:
        raise ProviderRateLimited("Feishu rate limited the request (HTTP 429)")
    if status >= 500:
        raise ProviderUnavailable(f"Feishu is unavailable (HTTP {status})")
    if status >= 400:
        code = _body_code(response)
        if code not in (None, 0):
            _raise_for_code(code)
        raise ProviderUnavailable(f"Feishu rejected the request (HTTP {status})")


class FeishuNotifier:
    """Send interactive cards to a Feishu chat.

    If ``client`` is supplied, the notifier reuses it and never closes it.
    Otherwise it owns an :class:`httpx.AsyncClient`; call :meth:`aclose` when
    finished with it.
    """

    def __init__(
        self,
        *,
        app_id: str,
        app_secret: str,
        base_url: str = "https://open.feishu.cn",
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._app_id = app_id
        self._app_secret = app_secret
        self._base_url = base_url.rstrip("/")
        self._owns_client = client is None
        self._client = client if client is not None else httpx.AsyncClient()
        self._tenant_token: str | None = None
        self._token_expires_at = 0.0

    @classmethod
    def from_config(
        cls,
        config: ProviderConfig,
        secrets: SecretResolver,
    ) -> FeishuNotifier:
        """Build a notifier from a provider config and a secret resolver.

        The app ID is read from the environment variable named by
        ``config.config["app_id_env"]`` (default ``GROWTH_FEISHU_APP_ID``);
        the app secret is resolved through ``secrets`` using
        ``config.secret_ref``. Error messages name the missing variable but
        never contain its value.
        """
        app_id_env = config.config.get("app_id_env", "GROWTH_FEISHU_APP_ID")
        app_id = os.environ.get(app_id_env)
        if not app_id:
            raise ProviderNotConfigured(
                f"SECRET_NOT_CONFIGURED: {app_id_env}"
            )
        app_secret = secrets.get(config.secret_ref)
        base_url = config.config.get("base_url", "https://open.feishu.cn")
        return cls(app_id=app_id, app_secret=app_secret, base_url=base_url)

    async def health(self) -> AdapterHealth:
        """Report readiness without making a network call."""
        if not self._app_id or not self._app_secret:
            return AdapterHealth(
                name="feishu",
                status="down",
                detail="Feishu app credentials are not configured",
            )
        if self._client is None:
            return AdapterHealth(
                name="feishu",
                status="down",
                detail="Feishu HTTP client is not available",
            )
        return AdapterHealth(name="feishu", status="ready")

    async def aclose(self) -> None:
        """Close the HTTP client only when this notifier owns it."""
        if self._owns_client and self._client is not None:
            await self._client.aclose()

    async def _get_tenant_token(self) -> str:
        now = time.time()
        if self._tenant_token and now < self._token_expires_at:
            return self._tenant_token

        try:
            response = await self._client.post(
                f"{self._base_url}{_TENANT_TOKEN_PATH}",
                json={"app_id": self._app_id, "app_secret": self._app_secret},
            )
        except httpx.TimeoutException as exc:
            raise ProviderUnavailable("Feishu token request timed out") from exc
        except httpx.HTTPError as exc:
            raise ProviderUnavailable("Feishu token request failed") from exc

        _raise_for_http_status(response)
        payload = _json_object(response, "token")
        code = payload.get("code")
        if code not in (None, 0):
            _raise_for_code(code)

        token = payload.get("tenant_access_token")
        if not isinstance(token, str) or not token:
            raise ProviderBadOutput(
                "Feishu token response was missing tenant_access_token"
            )

        try:
            expires_in = int(payload.get("expire", 0))
        except (TypeError, ValueError):
            expires_in = 0

        self._tenant_token = token
        self._token_expires_at = (
            time.time() + expires_in - _TOKEN_EXPIRY_SKEW_SECONDS
        )
        return token

    async def send_card(self, chat_id: str, card: dict[str, Any]) -> str:
        """Send ``card`` to ``chat_id`` and return Feishu's ``message_id``."""
        token = await self._get_tenant_token()

        try:
            response = await self._client.post(
                f"{self._base_url}{_SEND_MESSAGE_PATH}",
                params={"receive_id_type": "chat_id"},
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "receive_id": chat_id,
                    "msg_type": "interactive",
                    "content": json.dumps(card),
                },
            )
        except httpx.TimeoutException as exc:
            raise ProviderUnavailable("Feishu send request timed out") from exc
        except httpx.HTTPError as exc:
            raise ProviderUnavailable("Feishu send request failed") from exc

        _raise_for_http_status(response)
        payload = _json_object(response, "send")
        code = payload.get("code")
        if code != 0:
            _raise_for_code(code)

        data = payload.get("data")
        message_id = data.get("message_id") if isinstance(data, Mapping) else None
        if not isinstance(message_id, str) or not message_id:
            raise ProviderBadOutput(
                "Feishu send response was missing message_id"
            )
        return message_id


@register_adapter("notifier", "feishu")
def _feishu_factory(
    config: ProviderConfig, secrets: SecretResolver
) -> FeishuNotifier:
    return FeishuNotifier.from_config(config, secrets)
