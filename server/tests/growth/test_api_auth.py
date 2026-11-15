"""Tests for Growth Agent service-token auth, context, and social API skeleton."""

from __future__ import annotations

import asyncio
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from growth_core.config import GrowthSettings
from growth_core.schemas import NewOutreachMessage, NewSocialLead
from growth_social.main import create_social_app

TENANT_A = "00000000-0000-0000-0000-000000000001"
WORKSPACE_A = "00000000-0000-0000-0000-000000000002"
TENANT_B = "00000000-0000-0000-0000-000000000003"
WORKSPACE_B = "00000000-0000-0000-0000-000000000004"
SERVICE_TOKEN = "service-token"


def _settings(**overrides) -> GrowthSettings:
    values = {
        "database_url": "postgresql://unused",
        "service_token": SERVICE_TOKEN,
        "tenant_id": TENANT_A,
        "workspace_id": WORKSPACE_A,
    }
    values.update(overrides)
    return GrowthSettings(**values)


def _client(repo, **overrides) -> TestClient:
    return TestClient(create_social_app(settings=_settings(**overrides), repo=repo))


def _auth(token: str = SERVICE_TOKEN, **extra: str) -> dict[str, str]:
    headers = {"X-Service-Token": token}
    headers.update(extra)
    return headers


def _seed_lead(repo, tenant_id: str, workspace_id: str, post_id: str):
    return asyncio.run(
        repo.upsert_lead(
            NewSocialLead(
                tenant_id=UUID(tenant_id),
                workspace_id=UUID(workspace_id),
                platform="reddit",
                platform_post_id=post_id,
                title=f"title-{post_id}",
                body=f"body-{post_id}",
                source_url=f"https://example.test/{post_id}",
                dedupe_key=f"reddit:{post_id}",
            )
        )
    )[0]


def _seed_message(repo, tenant_id: str, workspace_id: str, dedupe_key: str):
    return asyncio.run(
        repo.create_message(
            NewOutreachMessage(
                tenant_id=UUID(tenant_id),
                workspace_id=UUID(workspace_id),
                channel="reddit",
                status="drafted",
                dedupe_key=dedupe_key,
            )
        )
    )


def test_internal_endpoint_requires_service_token(repo):
    client = _client(repo)
    response = client.post("/internal/v1/social/ingest", json={})
    assert response.status_code == 401


def test_internal_endpoint_enqueues_idempotent_ingest(repo):
    client = _client(repo)
    headers = {
        "X-Service-Token": SERVICE_TOKEN,
        "X-Tenant-Id": TENANT_A,
        "X-Workspace-Id": WORKSPACE_A,
        "Idempotency-Key": "ingest:2026-11-15T09:00",
    }
    first = client.post("/internal/v1/social/ingest", json={}, headers=headers)
    second = client.post("/internal/v1/social/ingest", json={}, headers=headers)
    assert first.status_code == 200
    assert first.json()["task_id"] == second.json()["task_id"]
    assert len(repo.tasks) == 1


def test_health_is_public(repo):
    client = _client(repo)
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ingest_requires_idempotency_key(repo):
    client = _client(repo)
    response = client.post("/internal/v1/social/ingest", json={}, headers=_auth())
    assert response.status_code == 400
    assert response.json()["detail"] == {"code": "INVALID_IDEMPOTENCY_KEY"}
    assert repo.tasks == []


@pytest.mark.parametrize(
    ("endpoint", "task_type", "prefix"),
    [
        ("score", "social.score", "score"),
        ("draft", "social.draft", "draft"),
    ],
)
def test_score_and_draft_derive_deterministic_keys(repo, endpoint, task_type, prefix):
    client = _client(repo)
    lead_id = uuid4()
    first = client.post(
        f"/internal/v1/social/{endpoint}",
        json={"lead_id": str(lead_id)},
        headers=_auth(),
    )
    second = client.post(
        f"/internal/v1/social/{endpoint}",
        json={"lead_id": str(lead_id)},
        headers=_auth(),
    )
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["task_id"] == second.json()["task_id"]
    assert len(repo.tasks) == 1
    task = repo.tasks[0]
    assert task.task_type == task_type
    assert task.payload == {"lead_id": str(lead_id)}
    assert task.idempotency_key == f"{prefix}:{lead_id}"


def test_read_leads_requires_token_and_is_tenant_scoped(repo):
    lead_a = _seed_lead(repo, TENANT_A, WORKSPACE_A, "a")
    lead_b = _seed_lead(repo, TENANT_B, WORKSPACE_B, "b")
    client = _client(repo)

    assert client.get("/api/growth/social/leads").status_code == 401

    response = client.get("/api/growth/social/leads", headers=_auth())
    assert response.status_code == 200
    assert [row["id"] for row in response.json()] == [str(lead_a.id)]

    override = client.get(
        "/api/growth/social/leads", headers=_auth(**{"X-Tenant-Id": TENANT_B})
    )
    assert override.status_code == 200
    assert [row["id"] for row in override.json()] == [str(lead_b.id)]


def test_read_messages_requires_token_and_is_tenant_scoped(repo):
    message_a = _seed_message(repo, TENANT_A, WORKSPACE_A, "reddit:a")
    _seed_message(repo, TENANT_B, WORKSPACE_B, "reddit:b")
    client = _client(repo)

    assert client.get("/api/growth/social/messages").status_code == 401

    response = client.get("/api/growth/social/messages", headers=_auth())
    assert response.status_code == 200
    assert [row["id"] for row in response.json()] == [str(message_a.id)]


def test_read_leads_clamps_limit(repo):
    _seed_lead(repo, TENANT_A, WORKSPACE_A, "a")
    _seed_lead(repo, TENANT_A, WORKSPACE_A, "b")
    client = _client(repo)
    response = client.get(
        "/api/growth/social/leads?limit=0", headers=_auth()
    )
    assert response.status_code == 200
    assert len(response.json()) == 1


def test_invalid_tenant_header_returns_400(repo):
    client = _client(repo)
    response = client.get(
        "/api/growth/social/leads",
        headers=_auth(**{"X-Tenant-Id": "not-a-uuid"}),
    )
    assert response.status_code == 400
    assert response.json()["detail"] == {"code": "INVALID_TENANT_ID"}


def test_invalid_workspace_header_returns_400(repo):
    client = _client(repo)
    response = client.get(
        "/api/growth/social/leads",
        headers=_auth(**{"X-Workspace-Id": "not-a-uuid"}),
    )
    assert response.status_code == 400
    assert response.json()["detail"] == {"code": "INVALID_WORKSPACE_ID"}


def test_empty_service_token_fails_closed(repo):
    client = _client(repo, service_token="")
    response = client.get(
        "/api/growth/social/leads", headers={"X-Service-Token": ""}
    )
    assert response.status_code == 401


def test_invalid_service_token_is_rejected_without_echo(repo):
    client = _client(repo)
    supplied = "wrong-token"
    response = client.post(
        "/internal/v1/social/ingest",
        json={},
        headers={"X-Service-Token": supplied, "Idempotency-Key": "ingest:x"},
    )
    assert response.status_code == 401
    assert supplied not in response.text
    assert SERVICE_TOKEN not in response.text
