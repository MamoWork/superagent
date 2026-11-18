"""Tests for Feishu approval callbacks and operator revision.

Approval only moves database state: nothing here posts a reply. The callback
is authenticated by the Feishu signature or verification token, never by the
service token, because Feishu cannot send one.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from growth_core.config import GrowthSettings
from growth_core.schemas import (
    NewApprovalRequest,
    NewOutreachMessage,
    NewOutreachVersion,
    SocialLead,
)
from growth_social.main import create_social_app
from growth_social.services.approval import (
    FeishuAction,
    handle_approval,
    parse_feishu_action,
)

CLOCK = datetime(2026, 11, 15, 9, 0, tzinfo=timezone.utc)

TENANT = UUID("00000000-0000-0000-0000-000000000001")
WORKSPACE = UUID("00000000-0000-0000-0000-000000000002")
SERVICE_TOKEN = "service-token"
VERIFICATION_TOKEN = "verify-token"
ENCRYPT_KEY = "encrypt-key"

VALID_URL = (
    "https://example.com/guides/churn"
    "?utm_source=reddit&utm_medium=reply&utm_campaign=lead"
)
VALID_BODY = (
    "That onboarding slog sounds painful. I built Example, and this checklist "
    f"helps: {VALID_URL}"
)


# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------


def _settings(**overrides) -> GrowthSettings:
    values = {
        "database_url": "postgresql://unused",
        "service_token": SERVICE_TOKEN,
        "tenant_id": str(TENANT),
        "workspace_id": str(WORKSPACE),
        "feishu_chat_id": "oc_chat",
        "product_url": "https://example.com",
        "product_domain": "example.com",
        "feishu_verification_token": VERIFICATION_TOKEN,
    }
    values.update(overrides)
    return GrowthSettings(**values)


def _client(repo, **overrides) -> TestClient:
    return TestClient(
        create_social_app(settings=_settings(**overrides), repo=repo)
    )


def _auth(**extra: str) -> dict[str, str]:
    headers = {"X-Service-Token": SERVICE_TOKEN}
    headers.update(extra)
    return headers


async def _seed_lead(repo, *, subreddit_rules=None) -> SocialLead:
    lead = SocialLead(
        id=uuid4(),
        tenant_id=TENANT,
        workspace_id=WORKSPACE,
        platform="reddit",
        platform_post_id=str(uuid4()),
        title="How do you keep onboarding emails personal?",
        body="Our welcome sequence feels generic after 200 signups.",
        source_url="https://reddit.example/r/SaaS/post/1",
        subreddit="SaaS",
        subreddit_rules=subreddit_rules or {},
        dedupe_key=str(uuid4()),
        status="draft_ready",
        score=91,
        created_at=CLOCK,
        updated_at=CLOCK,
    )
    repo.leads.append(lead)
    return lead


async def _seed_message(
    repo,
    lead: SocialLead,
    *,
    status: str = "draft_ready",
    version: int = 1,
    body_text: str = VALID_BODY,
):
    message = await repo.create_message(
        NewOutreachMessage(
            tenant_id=TENANT,
            workspace_id=WORKSPACE,
            channel="social",
            provider="reddit",
            lead_id=lead.id,
            status=status,
            dedupe_key=f"draft:{lead.id}",
            metadata={"draft_version": version},
        )
    )
    outreach_version = await repo.create_version(
        NewOutreachVersion(
            tenant_id=TENANT,
            message_id=message.id,
            version=version,
            body_text=body_text,
            cta_url=VALID_URL,
        )
    )
    return message, outreach_version


async def _seed_approval(repo, message, *, approval_id: str | None = None):
    return await repo.create_approval_request(
        NewApprovalRequest(
            tenant_id=TENANT,
            workspace_id=WORKSPACE,
            message_id=message.id,
            approval_id=approval_id or f"{message.id}:v1",
            provider="feishu",
            payload={"chat_id": "oc_chat"},
        )
    )


async def _seed(
    repo,
    *,
    status: str = "draft_ready",
    subreddit_rules=None,
):
    lead = await _seed_lead(repo, subreddit_rules=subreddit_rules)
    message, version = await _seed_message(repo, lead, status=status)
    approval = await _seed_approval(repo, message)
    return lead, message, version, approval


def _current_payload(approval_id: str, action: str, operator: str = "ou_1"):
    return {
        "schema": "2.0",
        "header": {"token": VERIFICATION_TOKEN, "event_type": "card.action"},
        "event": {
            "action": {"value": {"approval_id": approval_id, "action": action}},
            "operator": {"operator_id": {"open_id": operator}},
        },
    }


def _signed_headers(body: bytes) -> dict[str, str]:
    timestamp = "1700000000"
    nonce = "nonce-1"
    digest = hashlib.sha256(
        (timestamp + nonce + ENCRYPT_KEY).encode("utf-8") + body
    ).hexdigest()
    return {
        "X-Lark-Request-Timestamp": timestamp,
        "X-Lark-Request-Nonce": nonce,
        "X-Lark-Signature": digest,
        "Content-Type": "application/json",
    }


# ---------------------------------------------------------------------------
# parse_feishu_action
# ---------------------------------------------------------------------------


def test_parse_current_payload_shape():
    action = parse_feishu_action(_current_payload("abc:v1", "approve", "ou_9"))
    assert action == FeishuAction(
        approval_id="abc:v1", action="approve", operator="ou_9"
    )


def test_parse_legacy_payload_shape():
    action = parse_feishu_action(
        {
            "action": {"value": {"approval_id": "abc:v1", "action": "later"}},
            "open_id": "ou_legacy",
        }
    )
    assert action == FeishuAction(
        approval_id="abc:v1", action="later", operator="ou_legacy"
    )


def test_parse_missing_operator_is_none():
    payload = _current_payload("abc:v1", "reject")
    del payload["event"]["operator"]
    assert parse_feishu_action(payload).operator is None


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"event": {"action": {"value": {"action": "approve"}}}},
        {"event": {"action": {"value": {"approval_id": "", "action": "approve"}}}},
        {"event": {"action": {"value": {"approval_id": "x", "action": "send"}}}},
        {"event": {"action": {"value": "not-a-dict"}}},
    ],
    ids=["empty", "missing-id", "empty-id", "bad-action", "bad-value"],
)
def test_parse_malformed_payload_raises(payload):
    with pytest.raises(ValueError) as excinfo:
        parse_feishu_action(payload)
    assert str(excinfo.value) == "INVALID_FEISHU_ACTION"


# ---------------------------------------------------------------------------
# handle_approval
# ---------------------------------------------------------------------------


async def test_approve_transitions_message_and_version(repo, now):
    lead, message, version, approval = await _seed(repo)

    result = await handle_approval(
        repo,
        tenant_id=TENANT,
        action=FeishuAction(
            approval_id=approval.approval_id, action="approve", operator="ou_1"
        ),
        now=now,
    )

    assert result.status == "approved"
    assert result.message_id == message.id
    stored = await repo.get_message(TENANT, message.id)
    assert stored.status == "approved"
    latest = await repo.get_latest_version(TENANT, message.id)
    assert latest.approved_by == "ou_1"
    assert latest.approved_at == now
    stored_approval = await repo.get_approval_request(
        TENANT, approval.approval_id
    )
    assert stored_approval.status == "approved"
    assert stored_approval.decided_by == "ou_1"
    audits = [a for a in repo.audit if a["action"] == "social.approved"]
    assert len(audits) == 1
    assert audits[0]["actor_type"] == "user"
    assert audits[0]["actor_id"] == "ou_1"
    assert audits[0]["entity_id"] == message.id


async def test_approve_without_operator_uses_feishu(repo, now):
    _, message, _, approval = await _seed(repo)

    result = await handle_approval(
        repo,
        tenant_id=TENANT,
        action=FeishuAction(
            approval_id=approval.approval_id, action="approve", operator=None
        ),
        now=now,
    )

    assert result.status == "approved"
    latest = await repo.get_latest_version(TENANT, message.id)
    assert latest.approved_by == "feishu"


async def test_duplicate_approve_is_idempotent(repo, now):
    _, _, _, approval = await _seed(repo)
    action = FeishuAction(
        approval_id=approval.approval_id, action="approve", operator="ou_1"
    )

    first = await handle_approval(repo, tenant_id=TENANT, action=action, now=now)
    second = await handle_approval(
        repo, tenant_id=TENANT, action=action, now=now
    )

    assert first.status == "approved"
    assert second.status == "already_decided"
    assert len([a for a in repo.audit if a["action"] == "social.approved"]) == 1


async def test_reject_transitions_to_rejected(repo, now):
    _, message, _, approval = await _seed(repo)

    result = await handle_approval(
        repo,
        tenant_id=TENANT,
        action=FeishuAction(
            approval_id=approval.approval_id, action="reject", operator="ou_1"
        ),
        now=now,
    )

    assert result.status == "rejected"
    stored = await repo.get_message(TENANT, message.id)
    assert stored.status == "rejected"
    stored_approval = await repo.get_approval_request(
        TENANT, approval.approval_id
    )
    assert stored_approval.status == "rejected"
    assert stored_approval.reason == "feishu_reject"
    assert len([a for a in repo.audit if a["action"] == "social.rejected"]) == 1


async def test_approve_on_non_draft_ready_message_is_already_decided(repo, now):
    lead = await _seed_lead(repo)
    message, _ = await _seed_message(repo, lead, status="sent")
    approval = await _seed_approval(repo, message)

    result = await handle_approval(
        repo,
        tenant_id=TENANT,
        action=FeishuAction(
            approval_id=approval.approval_id, action="approve", operator="ou_1"
        ),
        now=now,
    )

    assert result.status == "already_decided"
    stored_approval = await repo.get_approval_request(
        TENANT, approval.approval_id
    )
    # The approval CAS ran first, but the version must not be marked approved.
    latest = await repo.get_latest_version(TENANT, message.id)
    assert latest.approved_by is None
    stored = await repo.get_message(TENANT, message.id)
    assert stored.status == "sent"


async def test_reject_conflict_still_stands_and_is_audited(repo, now):
    lead = await _seed_lead(repo)
    message, _ = await _seed_message(repo, lead, status="sent")
    approval = await _seed_approval(repo, message)

    result = await handle_approval(
        repo,
        tenant_id=TENANT,
        action=FeishuAction(
            approval_id=approval.approval_id, action="reject", operator="ou_1"
        ),
        now=now,
    )

    assert result.status == "rejected"
    stored_approval = await repo.get_approval_request(
        TENANT, approval.approval_id
    )
    assert stored_approval.status == "rejected"
    conflicts = [
        a for a in repo.audit if a["action"] == "social.approval_conflict"
    ]
    assert len(conflicts) == 1


@pytest.mark.parametrize("action", ["edit", "later"])
async def test_edit_and_later_change_nothing(repo, now, action):
    _, message, _, approval = await _seed(repo)

    result = await handle_approval(
        repo,
        tenant_id=TENANT,
        action=FeishuAction(
            approval_id=approval.approval_id, action=action, operator="ou_1"
        ),
        now=now,
    )

    assert result.status == "pending"
    assert result.message_id == message.id
    assert result.reason
    stored = await repo.get_message(TENANT, message.id)
    assert stored.status == "draft_ready"
    stored_approval = await repo.get_approval_request(
        TENANT, approval.approval_id
    )
    assert stored_approval.status == "pending"
    assert repo.audit == []


async def test_unknown_approval_is_not_found(repo, now):
    result = await handle_approval(
        repo,
        tenant_id=TENANT,
        action=FeishuAction(
            approval_id="missing:v1", action="approve", operator="ou_1"
        ),
        now=now,
    )
    assert result.status == "not_found"
    assert result.message_id is None


async def test_approve_message_cas_conflict_is_audited(repo, now):
    lead = await _seed_lead(repo)
    message, _ = await _seed_message(repo, lead, status="rejected")
    approval = await _seed_approval(repo, message)

    result = await handle_approval(
        repo,
        tenant_id=TENANT,
        action=FeishuAction(
            approval_id=approval.approval_id, action="approve", operator="ou_1"
        ),
        now=now,
    )

    assert result.status == "already_decided"
    conflicts = [
        a for a in repo.audit if a["action"] == "social.approval_conflict"
    ]
    assert len(conflicts) == 1
    assert conflicts[0]["actor_type"] == "service"
    assert conflicts[0]["entity_id"] == message.id
    assert conflicts[0]["after"] == {
        "approval_id": approval.approval_id,
        "expected_status": "draft_ready",
        "attempted_status": "approved",
    }
    latest = await repo.get_latest_version(TENANT, message.id)
    assert latest.approved_by is None


async def test_approve_marks_the_matching_version(repo, now):
    lead = await _seed_lead(repo)
    message, _ = await _seed_message(repo, lead)
    await repo.create_version(
        NewOutreachVersion(
            tenant_id=TENANT,
            message_id=message.id,
            version=2,
            body_text=VALID_BODY,
            cta_url=VALID_URL,
        )
    )
    approval = await _seed_approval(
        repo, message, approval_id=f"{message.id}:v2"
    )

    result = await handle_approval(
        repo,
        tenant_id=TENANT,
        action=FeishuAction(
            approval_id=approval.approval_id, action="approve", operator="ou_1"
        ),
        now=now,
    )

    assert result.status == "approved"
    latest = await repo.get_latest_version(TENANT, message.id)
    assert latest.version == 2
    assert latest.approved_by == "ou_1"
    conflicts = [
        a for a in repo.audit if a["action"] == "social.approval_conflict"
    ]
    assert conflicts == []


async def test_approve_does_not_mark_a_newer_version(repo, now):
    lead = await _seed_lead(repo)
    message, _ = await _seed_message(repo, lead)
    await repo.create_version(
        NewOutreachVersion(
            tenant_id=TENANT,
            message_id=message.id,
            version=2,
            body_text=VALID_BODY,
            cta_url=VALID_URL,
        )
    )
    approval = await _seed_approval(
        repo, message, approval_id=f"{message.id}:v1"
    )

    result = await handle_approval(
        repo,
        tenant_id=TENANT,
        action=FeishuAction(
            approval_id=approval.approval_id, action="approve", operator="ou_1"
        ),
        now=now,
    )

    assert result.status == "approved"
    latest = await repo.get_latest_version(TENANT, message.id)
    assert latest.version == 2
    assert latest.approved_by is None
    conflicts = [
        a for a in repo.audit if a["action"] == "social.approval_conflict"
    ]
    assert len(conflicts) == 1
    assert conflicts[0]["after"] == {
        "approval_id": approval.approval_id,
        "approved_version": 1,
        "latest_version": 2,
    }


async def test_approve_unparseable_approval_id_is_a_conflict(repo, now):
    lead = await _seed_lead(repo)
    message, _ = await _seed_message(repo, lead)
    approval = await _seed_approval(
        repo, message, approval_id="not-versioned"
    )

    result = await handle_approval(
        repo,
        tenant_id=TENANT,
        action=FeishuAction(
            approval_id="not-versioned", action="approve", operator="ou_1"
        ),
        now=now,
    )

    assert result.status == "approved"
    latest = await repo.get_latest_version(TENANT, message.id)
    assert latest.approved_by is None
    conflicts = [
        a for a in repo.audit if a["action"] == "social.approval_conflict"
    ]
    assert len(conflicts) == 1
    assert conflicts[0]["after"] == {
        "approval_id": "not-versioned",
        "approved_version": None,
        "latest_version": 1,
    }


# ---------------------------------------------------------------------------
# Callback endpoint
# ---------------------------------------------------------------------------


def test_callback_url_verification_challenge(repo):
    client = _client(repo)
    response = client.post(
        "/internal/v1/approvals/callback",
        json={
            "type": "url_verification",
            "challenge": "challenge-123",
            "token": VERIFICATION_TOKEN,
        },
    )
    assert response.status_code == 200
    assert response.json() == {"challenge": "challenge-123"}


def test_callback_requires_no_service_token_and_rejects_bad_token(repo):
    client = _client(repo)
    bad = client.post(
        "/internal/v1/approvals/callback",
        json={"type": "url_verification", "challenge": "x", "token": "wrong"},
    )
    assert bad.status_code == 403

    good = client.post(
        "/internal/v1/approvals/callback",
        json=_current_payload("missing:v1", "approve"),
    )
    assert good.status_code == 200


def test_callback_bad_signature_is_403(repo):
    client = _client(repo, feishu_encrypt_key=ENCRYPT_KEY)
    body = json.dumps(_current_payload("x", "approve")).encode()
    headers = _signed_headers(body)
    headers["X-Lark-Signature"] = "0" * 64
    response = client.post(
        "/internal/v1/approvals/callback", content=body, headers=headers
    )
    assert response.status_code == 403


def test_callback_invalid_json_is_400(repo):
    client = _client(repo)
    response = client.post(
        "/internal/v1/approvals/callback",
        content=b"{not json",
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 400


def test_callback_valid_event_approves(repo):
    client = _client(repo)

    async def seed():
        _, message, _, approval = await _seed(repo)
        return message, approval.approval_id

    message, approval_id = _run(seed())

    response = client.post(
        "/internal/v1/approvals/callback",
        json=_current_payload(approval_id, "approve", "ou_7"),
    )

    assert response.status_code == 200
    assert response.json()["toast"]["type"] == "success"
    stored = _run(repo.get_message(TENANT, message.id))
    assert stored.status == "approved"


def test_callback_signed_event_approves(repo):
    client = _client(repo, feishu_encrypt_key=ENCRYPT_KEY)
    async def seed():
        _, message, _, approval = await _seed(repo)
        return message, approval.approval_id

    message, approval_id = _run(seed())
    body = json.dumps(_current_payload(approval_id, "approve")).encode()

    response = client.post(
        "/internal/v1/approvals/callback",
        content=body,
        headers=_signed_headers(body),
    )

    assert response.status_code == 200
    assert response.json()["toast"]["type"] == "success"
    assert _run(repo.get_message(TENANT, message.id)).status == "approved"


def test_callback_unknown_approval_returns_error_toast(repo):
    client = _client(repo)
    response = client.post(
        "/internal/v1/approvals/callback",
        json=_current_payload("unknown:v1", "approve"),
    )
    assert response.status_code == 200
    assert response.json()["toast"]["type"] == "error"


def test_callback_legacy_payload_shape(repo):
    client = _client(repo)

    async def seed():
        _, message, _, approval = await _seed(repo)
        return message, approval.approval_id

    message, approval_id = _run(seed())

    response = client.post(
        "/internal/v1/approvals/callback",
        json={
            "token": VERIFICATION_TOKEN,
            "action": {"value": {"approval_id": approval_id, "action": "approve"}},
            "open_id": "ou_legacy",
        },
    )

    assert response.status_code == 200
    assert response.json()["toast"]["type"] == "success"
    assert _run(repo.get_message(TENANT, message.id)).status == "approved"


def test_callback_malformed_action_returns_error_toast(repo):
    client = _client(repo)
    response = client.post(
        "/internal/v1/approvals/callback",
        json={
            "token": VERIFICATION_TOKEN,
            "event": {
                "action": {
                    "value": {"approval_id": "x:v1", "action": "send"}
                }
            },
        },
    )
    assert response.status_code == 200
    assert response.json()["toast"]["type"] == "error"


# ---------------------------------------------------------------------------
# Revision endpoint
# ---------------------------------------------------------------------------


def _revise(client, message_id, body_markdown, operator="operator-1"):
    return client.post(
        f"/api/growth/social/messages/{message_id}/revise",
        json={"body_markdown": body_markdown, "operator": operator},
        headers=_auth(),
    )


def test_revise_creates_new_version_and_new_approval(repo):
    client = _client(repo)

    async def seed():
        return await _seed(repo)

    lead, message, old_version, old_approval = _run(seed())

    response = _revise(client, message.id, VALID_BODY.replace("checklist", "guide"))

    assert response.status_code == 200
    data = response.json()
    assert data["message_id"] == str(message.id)
    assert data["status"] == "draft_ready"
    assert data["version"] == 2
    new_approval_id = f"{message.id}:v2"
    assert data["approval_id"] == new_approval_id

    # Both versions survive; the old approval is expired, not deleted.
    versions = [
        v for v in repo.outreach_versions if v.message_id == message.id
    ]
    assert sorted(v.version for v in versions) == [1, 2]
    latest = _run(repo.get_latest_version(TENANT, message.id))
    assert latest.version == 2
    assert latest.body_text == VALID_BODY.replace("checklist", "guide")
    assert latest.cta_url == VALID_URL

    approvals = [a for a in repo.approvals if a.message_id == message.id]
    assert len(approvals) == 2
    by_id = {a.approval_id: a for a in approvals}
    assert by_id[old_approval.approval_id].status == "expired"
    assert by_id[new_approval_id].status == "pending"
    assert by_id[new_approval_id].workspace_id == WORKSPACE

    # Exactly one card row, keyed for the new approval.
    rows = [o for o in repo.outbox if o.payload.get("approval_id") == new_approval_id]
    assert len(rows) == 1
    assert rows[0].idempotency_key == f"feishu:{new_approval_id}"
    assert rows[0].topic == "feishu.card"
    assert len(repo.outbox) == 1

    stored = _run(repo.get_message(TENANT, message.id))
    assert stored.status == "draft_ready"
    assert stored.metadata["draft_version"] == 2

    audits = [a for a in repo.audit if a["action"] == "social.revised"]
    assert len(audits) == 1
    assert audits[0]["actor_type"] == "user"
    assert audits[0]["actor_id"] == "operator-1"
    assert audits[0]["after"] == {"version": 2}


def test_revise_from_approved_resets_to_draft_ready(repo):
    client = _client(repo)

    async def seed():
        lead, message, version, approval = await _seed(repo, status="approved")
        await repo.mark_version_approved(TENANT, version.id, "ou_1", CLOCK)
        return message

    message = _run(seed())

    response = _revise(client, message.id, VALID_BODY)

    assert response.status_code == 200
    assert response.json()["status"] == "draft_ready"
    stored = _run(repo.get_message(TENANT, message.id))
    assert stored.status == "draft_ready"
    assert _run(repo.get_latest_version(TENANT, message.id)).version == 2


def test_revise_invalid_policy_is_422(repo):
    client = _client(repo)

    async def seed():
        return await _seed(repo)

    lead, message, _, _ = _run(seed())

    response = _revise(client, message.id, "No link at all here.")

    assert response.status_code == 422
    assert response.json()["detail"] == {"violations": ["NO_LINK"]}
    # Nothing new was created.
    assert len(repo.outreach_versions) == 1
    assert len(repo.approvals) == 1
    assert repo.outbox == []


def test_revise_subreddit_without_links_is_422_manual_only(repo):
    client = _client(repo)

    async def seed():
        return await _seed(
            repo, subreddit_rules={"self_promotion_allowed": False}
        )

    lead, message, _, _ = _run(seed())

    response = _revise(client, message.id, VALID_BODY)

    assert response.status_code == 422
    assert "SUBREDDIT_NO_LINKS" in response.json()["detail"]["violations"]


def test_revise_on_sent_message_is_409(repo):
    client = _client(repo)

    async def seed():
        lead = await _seed_lead(repo)
        message, _ = await _seed_message(repo, lead, status="sent")
        await _seed_approval(repo, message)
        return message

    message = _run(seed())

    response = _revise(client, message.id, VALID_BODY)

    assert response.status_code == 409
    assert response.json()["detail"] == {"code": "MESSAGE_NOT_REVISABLE"}
    assert len(repo.outreach_versions) == 1
    assert repo.outbox == []


def test_revise_unique_violation_is_409_not_500(repo, monkeypatch):
    client = _client(repo)

    async def seed():
        return await _seed(repo)

    lead, message, _, _ = _run(seed())

    unique_error = type("UniqueViolationError", (Exception,), {})

    async def conflicting_create_version(version):
        raise unique_error("duplicate (message_id, version)")

    monkeypatch.setattr(repo, "create_version", conflicting_create_version)

    response = _revise(client, message.id, VALID_BODY)

    assert response.status_code == 409
    assert response.json()["detail"] == {"code": "REVISION_CONFLICT"}


@pytest.mark.parametrize(
    "payload",
    [
        {"body_markdown": VALID_BODY, "operator": ""},
        {"body_markdown": VALID_BODY},
    ],
    ids=["empty-operator", "missing-operator"],
)
def test_revise_operator_is_required_and_non_empty(repo, payload):
    client = _client(repo)
    response = client.post(
        f"/api/growth/social/messages/{uuid4()}/revise",
        json=payload,
        headers=_auth(),
    )
    assert response.status_code == 422


def test_revise_requires_service_token(repo):
    client = _client(repo)

    async def seed():
        return await _seed(repo)

    _, message, _, _ = _run(seed())

    response = client.post(
        f"/api/growth/social/messages/{message.id}/revise",
        json={"body_markdown": VALID_BODY, "operator": "operator-1"},
    )
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# Async bridge for sync TestClient tests
# ---------------------------------------------------------------------------


def _run(coro):
    import asyncio

    return asyncio.run(coro)
