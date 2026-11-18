"""Tests for the OpenAI-compatible LLM client and JSON extraction."""

from __future__ import annotations

from types import SimpleNamespace

import httpx
import openai
import pytest
from pydantic import BaseModel

import growth_core.adapters.llm as llm_module
from growth_core.adapters.base import (
    ProviderAuthError,
    ProviderBadOutput,
    ProviderNotConfigured,
    ProviderRateLimited,
    ProviderUnavailable,
)
from growth_core.adapters.llm import OpenAICompatibleLLM, extract_json
from growth_core.adapters.registry import AdapterRegistry, EnvSecretResolver
from growth_core.schemas import ProviderConfig

TENANT_ID = "00000000-0000-0000-0000-000000000001"
REQUEST = httpx.Request("POST", "https://llm.example/v1/chat/completions")

INVALID_JSON = "PROVIDER_BAD_OUTPUT: invalid JSON response"
MISSING_CONTENT = "PROVIDER_BAD_OUTPUT: missing completion content"
SCHEMA_FAILED = "PROVIDER_BAD_OUTPUT: schema validation failed"


class Score(BaseModel):
    value: int


def _completion(content: object) -> SimpleNamespace:
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
    )


class CapturingCompletions:
    def __init__(self, content: object = '{"value": 7}') -> None:
        self.calls: list[dict] = []
        self._content = content

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        return _completion(self._content)


class RaisingCompletions:
    def __init__(self, exc: BaseException) -> None:
        self._exc = exc

    async def create(self, **kwargs):
        raise self._exc


class ReturningCompletions:
    def __init__(self, response: object) -> None:
        self._response = response

    async def create(self, **kwargs):
        return self._response


def _llm(completions: object, *, model: str = "default-model") -> OpenAICompatibleLLM:
    stub = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    return OpenAICompatibleLLM(api_key="key", model=model, client=stub)


def _status_error(error_type, status: int):
    return error_type(
        "upstream failure", response=httpx.Response(status, request=REQUEST), body=None
    )


class RecordingSecrets:
    """Secret resolver that records the references it is asked for."""

    def __init__(self, values: dict[str, str]) -> None:
        self.values = values
        self.requested: list[str | None] = []

    def get(self, ref: str | None) -> str:
        self.requested.append(ref)
        if ref not in self.values:
            raise ProviderNotConfigured(f"SECRET_NOT_CONFIGURED: {ref}")
        return self.values[ref]


# ---------------------------------------------------------------------------
# extract_json
# ---------------------------------------------------------------------------


def test_extract_json_handles_code_fences():
    assert extract_json('```json\n{"value": 7}\n```') == {"value": 7}


def test_extract_json_handles_plain_code_fence():
    assert extract_json('```\n{"value": 7}\n```') == {"value": 7}


def test_extract_json_strips_surrounding_whitespace():
    assert extract_json('  \n {"value": 7} \n ') == {"value": 7}


def test_extract_json_handles_fence_with_leading_whitespace():
    assert extract_json('   ```json\n{"value": 7}\n```  ') == {"value": 7}


@pytest.mark.parametrize("text", ["", "   ", "\n\t "])
def test_extract_json_rejects_empty_text(text):
    with pytest.raises(ProviderBadOutput) as excinfo:
        extract_json(text)
    assert str(excinfo.value) == INVALID_JSON


@pytest.mark.parametrize("text", ["not json", "{", "```json\n{broken}\n```"])
def test_extract_json_rejects_invalid_json(text):
    with pytest.raises(ProviderBadOutput) as excinfo:
        extract_json(text)
    assert str(excinfo.value) == INVALID_JSON


@pytest.mark.parametrize("text", ["[1, 2]", '"hello"', "null", "7", "true"])
def test_extract_json_rejects_non_dict_json(text):
    with pytest.raises(ProviderBadOutput) as excinfo:
        extract_json(text)
    assert str(excinfo.value) == INVALID_JSON


# ---------------------------------------------------------------------------
# Outbound request shape
# ---------------------------------------------------------------------------


async def test_complete_json_sends_exact_request_kwargs():
    completions = CapturingCompletions()
    llm = _llm(completions)

    result = await llm.complete_json(system="sys", user="usr", schema=Score)

    assert isinstance(result, Score)
    assert result.value == 7
    assert completions.calls == [
        {
            "model": "default-model",
            "messages": [
                {"role": "system", "content": "sys"},
                {"role": "user", "content": "usr"},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0,
        }
    ]


async def test_complete_json_model_override_wins():
    completions = CapturingCompletions()
    llm = _llm(completions)

    await llm.complete_json(
        system="s", user="u", schema=Score, model="override-model"
    )

    assert completions.calls[0]["model"] == "override-model"


async def test_complete_json_preserves_message_order_and_roles():
    completions = CapturingCompletions()
    llm = _llm(completions)

    await llm.complete_json(system="first", user="second", schema=Score)

    messages = completions.calls[0]["messages"]
    assert messages == [
        {"role": "system", "content": "first"},
        {"role": "user", "content": "second"},
    ]


async def test_complete_json_requires_a_model_before_calling():
    completions = CapturingCompletions()
    llm = _llm(completions, model="")

    with pytest.raises(ProviderNotConfigured) as excinfo:
        await llm.complete_json(system="s", user="u", schema=Score)

    assert str(excinfo.value) == "PROVIDER_NOT_CONFIGURED: llm model"
    assert completions.calls == []


# ---------------------------------------------------------------------------
# Response content shapes
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "response",
    [
        None,
        SimpleNamespace(),
        SimpleNamespace(choices=None),
        SimpleNamespace(choices=[]),
        SimpleNamespace(choices=[None]),
        SimpleNamespace(choices=[SimpleNamespace()]),
        SimpleNamespace(choices=[SimpleNamespace(message=None)]),
        SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace())]),
        _completion(None),
        _completion(""),
        _completion({"value": 7}),
        _completion(7),
    ],
)
async def test_complete_json_rejects_missing_completion_content(response):
    llm = _llm(ReturningCompletions(response))

    with pytest.raises(ProviderBadOutput) as excinfo:
        await llm.complete_json(system="s", user="u", schema=Score)

    assert str(excinfo.value) == MISSING_CONTENT


async def test_complete_json_rejects_whitespace_only_content():
    llm = _llm(CapturingCompletions("   \n\t"))

    with pytest.raises(ProviderBadOutput) as excinfo:
        await llm.complete_json(system="s", user="u", schema=Score)

    assert str(excinfo.value) == INVALID_JSON


async def test_complete_json_rejects_unparseable_content():
    llm = _llm(CapturingCompletions("not json"))

    with pytest.raises(ProviderBadOutput) as excinfo:
        await llm.complete_json(system="s", user="u", schema=Score)

    assert str(excinfo.value) == INVALID_JSON


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------


async def test_complete_json_validates_schema():
    llm = _llm(CapturingCompletions('{"value": 7}'))

    result = await llm.complete_json(system="s", user="u", schema=Score)

    assert isinstance(result, Score)
    assert result.value == 7


async def test_complete_json_accepts_fenced_content():
    llm = _llm(CapturingCompletions('```json\n{"value": 3}\n```'))

    result = await llm.complete_json(system="s", user="u", schema=Score)

    assert result == Score(value=3)


async def test_complete_json_schema_failure_has_stable_message_and_no_payload():
    llm = _llm(CapturingCompletions('{"value": "not-an-integer"}'))

    with pytest.raises(ProviderBadOutput) as excinfo:
        await llm.complete_json(
            system="SYSTEM_PROMPT_MARKER", user="USER_PROMPT_MARKER", schema=Score
        )

    message = str(excinfo.value)
    assert message == SCHEMA_FAILED
    assert "not-an-integer" not in message
    assert "SYSTEM_PROMPT_MARKER" not in message
    assert "USER_PROMPT_MARKER" not in message


# ---------------------------------------------------------------------------
# SDK error mapping
# ---------------------------------------------------------------------------


async def test_complete_json_maps_authentication_error():
    exc = _status_error(openai.AuthenticationError, 401)
    llm = _llm(RaisingCompletions(exc))

    with pytest.raises(ProviderAuthError) as excinfo:
        await llm.complete_json(system="s", user="u", schema=Score)

    assert str(excinfo.value) == "PROVIDER_AUTH_ERROR: llm authentication failed"


async def test_complete_json_maps_rate_limit_error():
    exc = _status_error(openai.RateLimitError, 429)
    llm = _llm(RaisingCompletions(exc))

    with pytest.raises(ProviderRateLimited) as excinfo:
        await llm.complete_json(system="s", user="u", schema=Score)

    assert str(excinfo.value) == "PROVIDER_RATE_LIMITED: llm rate limited"
    assert excinfo.value.retry_after_seconds is None


async def test_complete_json_maps_timeout_error():
    llm = _llm(RaisingCompletions(openai.APITimeoutError(request=REQUEST)))

    with pytest.raises(ProviderUnavailable) as excinfo:
        await llm.complete_json(system="s", user="u", schema=Score)

    assert str(excinfo.value) == "PROVIDER_UNAVAILABLE: llm timeout"


async def test_complete_json_maps_connection_error_to_unavailable():
    llm = _llm(RaisingCompletions(openai.APIConnectionError(request=REQUEST)))

    with pytest.raises(ProviderUnavailable) as excinfo:
        await llm.complete_json(system="s", user="u", schema=Score)

    assert str(excinfo.value) == "PROVIDER_UNAVAILABLE: llm request failed"


async def test_complete_json_maps_generic_exception_to_unavailable():
    llm = _llm(RaisingCompletions(RuntimeError("raw body: PROMPT_MARKER")))

    with pytest.raises(ProviderUnavailable) as excinfo:
        await llm.complete_json(system="s", user="u", schema=Score)

    assert str(excinfo.value) == "PROVIDER_UNAVAILABLE: llm request failed"
    assert "PROMPT_MARKER" not in str(excinfo.value)
    assert "raw body" not in str(excinfo.value)


async def test_sdk_errors_never_echo_prompt_or_sdk_message():
    prompt = "PROMPT_SECRET_MARKER"
    llm = _llm(
        RaisingCompletions(
            _status_error(openai.AuthenticationError, 401)
        )
    )

    with pytest.raises(ProviderAuthError) as excinfo:
        await llm.complete_json(system=prompt, user=prompt, schema=Score)

    assert prompt not in str(excinfo.value)
    assert "upstream failure" not in str(excinfo.value)


# ---------------------------------------------------------------------------
# Client ownership
# ---------------------------------------------------------------------------


async def test_aclose_does_not_close_injected_client():
    class InjectedClient:
        def __init__(self) -> None:
            self.chat = SimpleNamespace(completions=CapturingCompletions())
            self.closed = False

        async def close(self) -> None:
            self.closed = True

    client = InjectedClient()
    llm = OpenAICompatibleLLM(api_key="k", model="m", client=client)

    await llm.aclose()

    assert client.closed is False


async def test_aclose_closes_self_created_client(monkeypatch):
    created: list = []

    class FakeAsyncOpenAI:
        def __init__(self, **kwargs) -> None:
            self.kwargs = kwargs
            self.closed = False
            created.append(self)

        async def close(self) -> None:
            self.closed = True

    monkeypatch.setattr(llm_module, "AsyncOpenAI", FakeAsyncOpenAI)

    llm = OpenAICompatibleLLM(
        api_key="secret-key",
        model="m",
        base_url="https://llm.example/v1",
        timeout=12.5,
    )
    assert created[0].kwargs == {
        "api_key": "secret-key",
        "base_url": "https://llm.example/v1",
        "timeout": 12.5,
    }
    assert created[0].closed is False

    await llm.aclose()

    assert created[0].closed is True


# ---------------------------------------------------------------------------
# from_config and registration
# ---------------------------------------------------------------------------


def _config(**overrides) -> ProviderConfig:
    data = {
        "tenant_id": TENANT_ID,
        "capability": "llm",
        "provider": "openai_compatible",
        "config": {},
        "secret_ref": "GROWTH_LLM_API_KEY",
    }
    data.update(overrides)
    return ProviderConfig(**data)


def test_from_config_resolves_secret_and_reads_config():
    secrets = RecordingSecrets({"GROWTH_LLM_API_KEY": "resolved-key"})
    config = _config(
        config={
            "base_url": "https://llm.example/v1",
            "model": "configured-model",
            "timeout": 5.0,
        }
    )

    llm = OpenAICompatibleLLM.from_config(config, secrets)

    assert secrets.requested == ["GROWTH_LLM_API_KEY"]
    assert llm._api_key == "resolved-key"
    assert llm._base_url == "https://llm.example/v1"
    assert llm._model == "configured-model"
    assert llm._timeout == 5.0


def test_from_config_uses_defaults():
    secrets = RecordingSecrets({"GROWTH_LLM_API_KEY": "k"})
    config = _config(config={})

    llm = OpenAICompatibleLLM.from_config(config, secrets)

    assert llm._model == ""
    assert llm._base_url is None
    assert llm._timeout == 60.0


def test_from_config_propagates_missing_secret():
    config = _config(secret_ref="MISSING_LLM_KEY")

    with pytest.raises(ProviderNotConfigured) as excinfo:
        OpenAICompatibleLLM.from_config(config, RecordingSecrets({}))

    assert str(excinfo.value) == "SECRET_NOT_CONFIGURED: MISSING_LLM_KEY"


async def test_registry_resolves_openai_compatible_llm(monkeypatch):
    monkeypatch.setenv("GROWTH_LLM_API_KEY", "env-key")
    config = _config(config={"base_url": "https://llm.example/v1"})

    llm = AdapterRegistry([config], EnvSecretResolver()).llm()

    try:
        assert isinstance(llm, OpenAICompatibleLLM)
        assert llm._api_key == "env-key"
        assert llm._base_url == "https://llm.example/v1"
    finally:
        await llm.aclose()
