"""OpenAI-compatible LLM adapter.

Calls an OpenAI-compatible ``/chat/completions`` endpoint with a JSON response
format and validates the returned JSON against a pydantic model. Error
messages are stable, secret-free codes: prompts, completions, SDK exception
text, credentials, and authorization headers are never embedded in a raised
error.
"""

from __future__ import annotations

import json
from typing import Any

import openai
from openai import AsyncOpenAI
from pydantic import BaseModel, ValidationError

from growth_core.adapters.base import (
    ProviderAuthError,
    ProviderBadOutput,
    ProviderNotConfigured,
    ProviderRateLimited,
    ProviderUnavailable,
    SecretResolver,
)
from growth_core.adapters.registry import register_adapter
from growth_core.schemas import ProviderConfig

__all__ = ["OpenAICompatibleLLM", "extract_json"]

_DEFAULT_TIMEOUT = 60.0
_FENCE_PREFIXES = ("```json", "```")
_FENCE_SUFFIX = "```"

_INVALID_JSON = "PROVIDER_BAD_OUTPUT: invalid JSON response"
_MISSING_CONTENT = "PROVIDER_BAD_OUTPUT: missing completion content"
_SCHEMA_FAILED = "PROVIDER_BAD_OUTPUT: schema validation failed"


def extract_json(text: str) -> dict[str, Any]:
    """Parse a JSON object from ``text``, tolerating a Markdown code fence.

    Any failure — empty input, invalid JSON, or a parsed value that is not an
    object — raises :class:`ProviderBadOutput` with a stable message.
    """
    stripped = text.strip() if isinstance(text, str) else ""

    for prefix in _FENCE_PREFIXES:
        if stripped.startswith(prefix):
            stripped = stripped[len(prefix) :]
            break
    if stripped.endswith(_FENCE_SUFFIX):
        stripped = stripped[: -len(_FENCE_SUFFIX)]
    stripped = stripped.strip()

    try:
        data = json.loads(stripped)
    except (TypeError, ValueError) as exc:
        raise ProviderBadOutput(_INVALID_JSON) from exc
    if not isinstance(data, dict):
        raise ProviderBadOutput(_INVALID_JSON)
    return data


def _completion_content(response: Any) -> str:
    """Return the non-empty text content of the first completion choice."""
    try:
        content = response.choices[0].message.content
    except (AttributeError, IndexError, KeyError, TypeError) as exc:
        raise ProviderBadOutput(_MISSING_CONTENT) from exc
    if not isinstance(content, str) or not content:
        raise ProviderBadOutput(_MISSING_CONTENT)
    return content


class OpenAICompatibleLLM:
    """LLM adapter for any OpenAI-compatible chat completions endpoint.

    If ``client`` is supplied, the adapter reuses it and never closes it.
    Otherwise it owns an :class:`~openai.AsyncOpenAI`; call :meth:`aclose` when
    finished with it.
    """

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str | None = None,
        timeout: float = _DEFAULT_TIMEOUT,
        client: Any | None = None,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._base_url = base_url
        self._timeout = timeout
        self._owns_client = client is None
        self._client = (
            client
            if client is not None
            else AsyncOpenAI(api_key=api_key, base_url=base_url, timeout=timeout)
        )

    @classmethod
    def from_config(
        cls,
        config: ProviderConfig,
        secrets: SecretResolver,
    ) -> OpenAICompatibleLLM:
        """Build a client from a provider config and a secret resolver.

        ``base_url``, ``model``, and ``timeout`` come from ``config.config``;
        the API key is resolved through ``secrets`` using ``config.secret_ref``.
        The seeded config normally omits ``model`` because callers pass their
        own model on each request.
        """
        base_url = config.config.get("base_url")
        model = config.config.get("model", "")
        timeout = config.config.get("timeout", _DEFAULT_TIMEOUT)
        api_key = secrets.get(config.secret_ref)
        return cls(
            api_key=api_key,
            model=model,
            base_url=base_url,
            timeout=timeout,
        )

    async def aclose(self) -> None:
        """Close the SDK client only when this adapter owns it."""
        if self._owns_client:
            await self._client.close()

    async def complete_json(
        self,
        *,
        system: str,
        user: str,
        schema: type[BaseModel],
        model: str | None = None,
    ) -> BaseModel:
        """Request a JSON object and validate it as ``schema``."""
        final_model = model or self._model
        if not final_model:
            raise ProviderNotConfigured("PROVIDER_NOT_CONFIGURED: llm model")

        try:
            response = await self._client.chat.completions.create(
                model=final_model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                response_format={"type": "json_object"},
                temperature=0,
            )
        except openai.AuthenticationError as exc:
            raise ProviderAuthError(
                "PROVIDER_AUTH_ERROR: llm authentication failed"
            ) from exc
        except openai.RateLimitError as exc:
            raise ProviderRateLimited(
                "PROVIDER_RATE_LIMITED: llm rate limited",
                retry_after_seconds=None,
            ) from exc
        except openai.APITimeoutError as exc:
            raise ProviderUnavailable("PROVIDER_UNAVAILABLE: llm timeout") from exc
        except Exception as exc:
            raise ProviderUnavailable(
                "PROVIDER_UNAVAILABLE: llm request failed"
            ) from exc

        content = _completion_content(response)
        data = extract_json(content)
        try:
            return schema.model_validate(data)
        except ValidationError as exc:
            raise ProviderBadOutput(_SCHEMA_FAILED) from exc


@register_adapter("llm", "openai_compatible")
def _llm_factory(
    config: ProviderConfig, secrets: SecretResolver
) -> OpenAICompatibleLLM:
    return OpenAICompatibleLLM.from_config(config, secrets)
