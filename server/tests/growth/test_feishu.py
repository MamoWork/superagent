"""Tests for the Feishu notifier, callback verification, and fake notifier."""

from __future__ import annotations

import hashlib
import json

import httpx
import pytest

from growth_core.adapters.base import (
    AdapterHealth,
    ProviderAuthError,
    ProviderBadOutput,
    ProviderRateLimited,
    ProviderUnavailable,
)
from growth_core.adapters.feishu import FeishuNotifier
from growth_core.services.feishu_signature import (
    verify_feishu_signature,
    verify_feishu_token,
)
from tests.growth.fakes import FakeNotifier

TOKEN = "tenant-token-123"
SECRET = "app-secret-do-not-leak"


def _is_token_request(request: httpx.Request) -> bool:
    return request.url.path.endswith("/tenant_access_token/internal")


def _token_response(expire: int = 7200) -> httpx.Response:
    return httpx.Response(
        200, json={"tenant_access_token": TOKEN, "expire": expire}
    )


def _message_response(message_id: str = "om_1") -> httpx.Response:
    return httpx.Response(200, json={"code": 0, "data": {"message_id": message_id}})


# ---------------------------------------------------------------------------
# Signature verification
# ---------------------------------------------------------------------------


def test_feishu_signature_matches_official_formula():
    ts, nonce, key, body = "1700000000", "abc", "encrypt-key", b'{"hello":"world"}'
    expected = hashlib.sha256(
        (ts + nonce + key).encode("utf-8") + body
    ).hexdigest()
    headers = {
        "x-lark-request-timestamp": ts,
        "x-lark-request-nonce": nonce,
        "x-lark-signature": expected,
    }
    assert verify_feishu_signature(headers, body, key) is True


def test_feishu_signature_rejects_tampering():
    headers = {
        "x-lark-request-timestamp": "1700000000",
        "x-lark-request-nonce": "abc",
        "x-lark-signature": "bad",
    }
    assert verify_feishu_signature(headers, b"{}", "encrypt-key") is False


def test_feishu_signature_rejects_modified_body():
    ts, nonce, key = "1700000000", "abc", "encrypt-key"
    original = b'{"hello":"world"}'
    signature = hashlib.sha256(
        (ts + nonce + key).encode("utf-8") + original
    ).hexdigest()
    headers = {
        "x-lark-request-timestamp": ts,
        "x-lark-request-nonce": nonce,
        "x-lark-signature": signature,
    }
    assert verify_feishu_signature(headers, b'{"hello":"tampered"}', key) is False


def test_feishu_signature_accepts_uppercase_header_names():
    ts, nonce, key, body = "1700000000", "abc", "encrypt-key", b'{"hello":"world"}'
    expected = hashlib.sha256(
        (ts + nonce + key).encode("utf-8") + body
    ).hexdigest()
    headers = {
        "X-Lark-Request-Timestamp": ts,
        "X-Lark-Request-Nonce": nonce,
        "X-Lark-Signature": expected,
    }
    assert verify_feishu_signature(headers, body, key) is True


def test_feishu_signature_fails_closed_without_headers():
    assert verify_feishu_signature({}, b"{}", "encrypt-key") is False


# ---------------------------------------------------------------------------
# Callback token verification
# ---------------------------------------------------------------------------


def test_feishu_token_accepts_header_token():
    payload = {"header": {"token": "verify-token"}}
    assert verify_feishu_token(payload, "verify-token") is True


def test_feishu_token_falls_back_to_top_level_token():
    assert verify_feishu_token({"token": "verify-token"}, "verify-token") is True


def test_feishu_token_rejects_wrong_token():
    assert verify_feishu_token({"header": {"token": "wrong"}}, "expected") is False


def test_feishu_token_rejects_empty_expected_token():
    payload = {"header": {"token": "anything"}}
    assert verify_feishu_token(payload, "") is False


def test_feishu_token_prefers_header_token_over_top_level():
    payload = {"header": {"token": "wrong"}, "token": "expected"}
    assert verify_feishu_token(payload, "expected") is False


# ---------------------------------------------------------------------------
# Notifier
# ---------------------------------------------------------------------------


async def test_feishu_notifier_posts_interactive_card():
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if _is_token_request(request):
            return _token_response()
        return _message_response()

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler)
    ) as client:
        notifier = FeishuNotifier(
            app_id="app",
            app_secret=SECRET,
            client=client,
            base_url="https://open.feishu.cn",
        )
        message_id = await notifier.send_card("oc_1", {"config": {}})

    assert message_id == "om_1"
    send_calls = [call for call in calls if not _is_token_request(call)]
    assert len(send_calls) == 1
    send = send_calls[0]
    assert send.method == "POST"
    assert send.url.path.endswith("/open-apis/im/v1/messages")
    assert send.url.params["receive_id_type"] == "chat_id"
    assert send.headers["Authorization"] == f"Bearer {TOKEN}"
    body = json.loads(send.content)
    assert body["receive_id"] == "oc_1"
    assert body["msg_type"] == "interactive"
    assert json.loads(body["content"]) == {"config": {}}


async def test_feishu_notifier_caches_tenant_token():
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if _is_token_request(request):
            return _token_response()
        return _message_response("om_cached")

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler)
    ) as client:
        notifier = FeishuNotifier(
            app_id="app", app_secret=SECRET, client=client
        )
        assert await notifier.send_card("oc_1", {}) == "om_cached"
        assert await notifier.send_card("oc_2", {}) == "om_cached"

    token_calls = [call for call in calls if _is_token_request(call)]
    assert len(token_calls) == 1
    assert len(calls) == 3


async def test_feishu_notifier_maps_http_401_to_auth_error():
    def handler(request: httpx.Request) -> httpx.Response:
        if _is_token_request(request):
            return _token_response()
        return httpx.Response(401, json={"code": 99991663, "msg": "bad token"})

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler)
    ) as client:
        notifier = FeishuNotifier(
            app_id="app", app_secret=SECRET, client=client
        )
        with pytest.raises(ProviderAuthError):
            await notifier.send_card("oc_1", {})


async def test_feishu_notifier_maps_auth_code_to_auth_error():
    def handler(request: httpx.Request) -> httpx.Response:
        if _is_token_request(request):
            return _token_response()
        return httpx.Response(200, json={"code": 99991663, "msg": "bad token"})

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler)
    ) as client:
        notifier = FeishuNotifier(
            app_id="app", app_secret=SECRET, client=client
        )
        with pytest.raises(ProviderAuthError):
            await notifier.send_card("oc_1", {})


async def test_feishu_notifier_maps_http_429_to_rate_limited():
    def handler(request: httpx.Request) -> httpx.Response:
        if _is_token_request(request):
            return _token_response()
        return httpx.Response(429, json={"code": 99991400, "msg": "too many"})

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler)
    ) as client:
        notifier = FeishuNotifier(
            app_id="app", app_secret=SECRET, client=client
        )
        with pytest.raises(ProviderRateLimited):
            await notifier.send_card("oc_1", {})


async def test_feishu_notifier_maps_rate_limit_code_to_rate_limited():
    def handler(request: httpx.Request) -> httpx.Response:
        if _is_token_request(request):
            return _token_response()
        return httpx.Response(200, json={"code": 99991400, "msg": "too many"})

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler)
    ) as client:
        notifier = FeishuNotifier(
            app_id="app", app_secret=SECRET, client=client
        )
        with pytest.raises(ProviderRateLimited):
            await notifier.send_card("oc_1", {})


async def test_feishu_notifier_maps_http_500_to_unavailable():
    def handler(request: httpx.Request) -> httpx.Response:
        if _is_token_request(request):
            return _token_response()
        return httpx.Response(500, json={"code": 10000, "msg": "boom"})

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler)
    ) as client:
        notifier = FeishuNotifier(
            app_id="app", app_secret=SECRET, client=client
        )
        with pytest.raises(ProviderUnavailable):
            await notifier.send_card("oc_1", {})


async def test_feishu_notifier_maps_timeout_to_unavailable():
    def handler(request: httpx.Request) -> httpx.Response:
        if _is_token_request(request):
            return _token_response()
        raise httpx.ReadTimeout("timed out", request=request)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler)
    ) as client:
        notifier = FeishuNotifier(
            app_id="app", app_secret=SECRET, client=client
        )
        with pytest.raises(ProviderUnavailable):
            await notifier.send_card("oc_1", {})


async def test_feishu_notifier_maps_missing_message_id_to_bad_output():
    def handler(request: httpx.Request) -> httpx.Response:
        if _is_token_request(request):
            return _token_response()
        return httpx.Response(200, json={"code": 0, "data": {}})

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler)
    ) as client:
        notifier = FeishuNotifier(
            app_id="app", app_secret=SECRET, client=client
        )
        with pytest.raises(ProviderBadOutput):
            await notifier.send_card("oc_1", {})


async def test_feishu_notifier_unknown_code_includes_code_but_no_secrets():
    def handler(request: httpx.Request) -> httpx.Response:
        if _is_token_request(request):
            return _token_response()
        return httpx.Response(200, json={"code": 12345, "msg": "nope"})

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler)
    ) as client:
        notifier = FeishuNotifier(
            app_id="app", app_secret=SECRET, client=client
        )
        with pytest.raises(ProviderUnavailable) as excinfo:
            await notifier.send_card("oc_1", {})

    message = str(excinfo.value)
    assert "12345" in message
    assert SECRET not in message
    assert TOKEN not in message


# ---------------------------------------------------------------------------
# Health and client ownership
# ---------------------------------------------------------------------------


async def test_feishu_notifier_health_makes_no_request_and_reports_ready():
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(500)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler)
    ) as client:
        notifier = FeishuNotifier(
            app_id="app", app_secret=SECRET, client=client
        )
        health = await notifier.health()

    assert health == AdapterHealth(name="feishu", status="ready")
    assert calls == []


async def test_feishu_notifier_health_reports_down_without_credentials():
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(500))
    ) as client:
        notifier = FeishuNotifier(app_id="", app_secret="", client=client)
        health = await notifier.health()

    assert health.name == "feishu"
    assert health.status == "down"
    assert health.detail
    assert SECRET not in health.detail


async def test_feishu_notifier_does_not_close_injected_client():
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200))
    )
    notifier = FeishuNotifier(app_id="app", app_secret=SECRET, client=client)

    await notifier.aclose()

    assert client.is_closed is False
    await client.aclose()


async def test_feishu_notifier_closes_owned_client():
    notifier = FeishuNotifier(app_id="app", app_secret=SECRET)

    await notifier.aclose()

    assert notifier._client.is_closed is True


# ---------------------------------------------------------------------------
# Fake notifier
# ---------------------------------------------------------------------------


async def test_fake_notifier_records_cards_and_returns_ids():
    notifier = FakeNotifier()

    assert await notifier.send_card("oc_1", {"a": 1}) == "fake-1"
    assert await notifier.send_card("oc_2", {"b": 2}) == "fake-2"

    assert notifier.cards == [{"a": 1}, {"b": 2}]
    assert notifier.calls == [("oc_1", {"a": 1}), ("oc_2", {"b": 2})]
    health = await notifier.health()
    assert health == AdapterHealth(name="fake", status="ready")
