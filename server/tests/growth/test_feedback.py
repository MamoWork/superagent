"""Tests for the inbound feedback / unsubscribe write path."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from growth_core.config import GrowthSettings
from growth_core.schemas import SocialLead
from growth_social.main import create_social_app
from growth_social.services.feedback import (
    FeedbackLeadNotFound,
    record_feedback,
)

CLOCK = datetime(2026, 11, 15, 9, 0, tzinfo=timezone.utc)

TENANT = UUID("00000000-0000-0000-0000-000000000001")
WORKSPACE = UUID("00000000-0000-0000-0000-000000000002")
SERVICE_TOKEN = "service-token"


def _settings(**overrides) -> GrowthSettings:
    values = {
        "database_url": "postgresql://unused",
        "service_token": SERVICE_TOKEN,
        "tenant_id": str(TENANT),
        "workspace_id": str(WORKSPACE),
        "feishu_chat_id": "oc_chat",
        "product_url": "https://example.com",
        "product_domain": "example.com",
        "feishu_verification_token": "verify-token",
    }
    values.update(overrides)
    return GrowthSettings(**values)


def _client(repo) -> TestClient:
    return TestClient(create_social_app(settings=_settings(), repo=repo))


def _run(coro):
    return asyncio.run(coro)


def _seed_lead(
    repo,
    *,
    status: str = "qualified",
    author_public: str | None = "alice",
) -> SocialLead:
    lead = SocialLead(
        id=uuid4(),
        tenant_id=TENANT,
        workspace_id=WORKSPACE,
        platform="reddit",
        platform_post_id=str(uuid4()),
        title="How do you keep onboarding emails personal?",
        body="Our welcome sequence feels generic after 200 signups.",
        author_public=author_public,
        source_url="https://reddit.example/r/SaaS/post/1",
        subreddit="SaaS",
        dedupe_key=str(uuid4()),
        status=status,
        created_at=CLOCK,
        updated_at=CLOCK,
    )
    repo.leads.append(lead)
    return lead


async def _feedback(repo, lead, **kwargs):
    return await record_feedback(
        repo,
        tenant_id=TENANT,
        lead_id=lead.id,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Service behaviour
# ---------------------------------------------------------------------------


async def test_replied_marks_lead_replied_and_audits(repo):
    lead = _seed_lead(repo)

    result = await _feedback(
        repo, lead, kind="replied", evidence="author replied in thread"
    )

    assert result.lead_id == lead.id
    assert result.status == "replied"
    assert result.suppressed is False
    stored = await repo.get_lead(TENANT, lead.id)
    assert stored.status == "replied"
    # A reply changes the lead status but does not suppress the author.
    assert repo.suppressions == {}
    audits = [a for a in repo.audit if a["action"] == "social.feedback"]
    assert len(audits) == 1
    entry = audits[0]
    assert entry["actor_type"] == "integration"
    assert entry["actor_id"] == "api"
    assert entry["entity_type"] == "social_lead"
    assert entry["entity_id"] == lead.id
    assert entry["after"] == {
        "kind": "replied",
        "evidence": "author replied in thread",
        "status": "replied",
        "suppressed": False,
    }


@pytest.mark.parametrize(
    ("kind", "expected_reason"),
    [
        ("negative", "negative_reply"),
        ("unsubscribe", "unsubscribe"),
        ("moderator_warning", "moderator_warning"),
    ],
)
async def test_negative_kinds_suppress_lead_and_author(
    repo, kind, expected_reason
):
    lead = _seed_lead(repo)

    result = await _feedback(repo, lead, kind=kind, source="user")

    assert result.status == "suppressed"
    assert result.suppressed is True
    stored = await repo.get_lead(TENANT, lead.id)
    assert stored.status == "suppressed"
    assert await repo.is_suppressed(
        TENANT, "platform_user", f"{lead.platform}:{lead.author_public}"
    )
    assert repo.suppressions[
        (TENANT, "platform_user", f"{lead.platform}:{lead.author_public}")
    ][0] == expected_reason
    audits = [a for a in repo.audit if a["action"] == "social.feedback"]
    assert len(audits) == 1
    assert audits[0]["actor_type"] == "user"
    assert audits[0]["actor_id"] == "user"
    assert audits[0]["after"]["kind"] == kind
    assert audits[0]["after"]["suppressed"] is True


async def test_private_author_is_not_added_to_suppression_list(repo):
    lead = _seed_lead(repo, author_public=None)

    await _feedback(repo, lead, kind="unsubscribe")

    assert repo.suppressions == {}


@pytest.mark.parametrize("author_public", ["", "  ", "[deleted]"])
async def test_deleted_author_is_not_added_to_suppression_list(
    repo, author_public
):
    lead = _seed_lead(repo, author_public=author_public)

    await _feedback(repo, lead, kind="unsubscribe")

    assert repo.suppressions == {}


async def test_repeated_feedback_is_idempotent_and_audits_each_call(repo):
    lead = _seed_lead(repo)

    first = await _feedback(repo, lead, kind="negative")
    second = await _feedback(repo, lead, kind="negative")

    assert (first.status, second.status) == ("suppressed", "suppressed")
    assert (first.suppressed, second.suppressed) == (True, True)
    assert len(repo.suppressions) == 1
    # Every genuine feedback call is audited, including repeats.
    assert len([a for a in repo.audit if a["action"] == "social.feedback"]) == 2


@pytest.mark.parametrize("kind", ["replied", "negative", "unsubscribe"])
async def test_converted_lead_is_not_downgraded_but_is_audited(repo, kind):
    lead = _seed_lead(repo, status="converted")

    result = await _feedback(repo, lead, kind=kind)

    assert result.status == "converted"
    assert result.suppressed is False
    stored = await repo.get_lead(TENANT, lead.id)
    assert stored.status == "converted"
    audits = [a for a in repo.audit if a["action"] == "social.feedback"]
    assert len(audits) == 1
    assert audits[0]["after"]["status"] == "converted"
    assert audits[0]["after"]["suppressed"] is False


async def test_lost_cas_reloads_and_retries(repo, monkeypatch):
    lead = _seed_lead(repo)
    original = repo.update_lead_status
    calls = 0

    async def first_attempt_lost(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            # Simulate a concurrent writer moving the lead before our CAS.
            lead.status = "watch"
            return False
        return await original(*args, **kwargs)

    monkeypatch.setattr(repo, "update_lead_status", first_attempt_lost)

    result = await _feedback(repo, lead, kind="negative")

    assert calls == 2
    assert result.status == "suppressed"
    stored = await repo.get_lead(TENANT, lead.id)
    assert stored.status == "suppressed"
    assert len([a for a in repo.audit if a["action"] == "social.feedback"]) == 1


async def test_cas_retry_is_bounded_and_still_audits(repo, monkeypatch):
    lead = _seed_lead(repo)
    calls = 0

    async def always_lost(*args, **kwargs):
        nonlocal calls
        calls += 1
        return False

    monkeypatch.setattr(repo, "update_lead_status", always_lost)

    result = await _feedback(repo, lead, kind="negative")

    assert calls == 3
    assert result.status == "qualified"
    stored = await repo.get_lead(TENANT, lead.id)
    assert stored.status == "qualified"
    audits = [a for a in repo.audit if a["action"] == "social.feedback"]
    assert len(audits) == 1
    assert audits[0]["after"]["status"] == "qualified"


async def test_unknown_lead_raises(repo):
    with pytest.raises(FeedbackLeadNotFound):
        await record_feedback(
            repo,
            tenant_id=TENANT,
            lead_id=uuid4(),
            kind="replied",
        )

    assert repo.audit == []


# ---------------------------------------------------------------------------
# HTTP endpoint
# ---------------------------------------------------------------------------


def test_api_feedback_happy_path(repo):
    lead = _seed_lead(repo)

    response = _client(repo).post(
        "/internal/v1/social/feedback",
        json={
            "lead_id": str(lead.id),
            "kind": "moderator_warning",
            "evidence": "subreddit mod removed the reply",
            "source": "reddit",
        },
        headers={"X-Service-Token": SERVICE_TOKEN},
    )

    assert response.status_code == 200
    assert response.json() == {
        "lead_id": str(lead.id),
        "status": "suppressed",
        "suppressed": True,
    }
    stored = _run(repo.get_lead(TENANT, lead.id))
    assert stored.status == "suppressed"


def test_api_feedback_unknown_lead_is_404(repo):
    response = _client(repo).post(
        "/internal/v1/social/feedback",
        json={"lead_id": str(uuid4()), "kind": "replied"},
        headers={"X-Service-Token": SERVICE_TOKEN},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == {"code": "LEAD_NOT_FOUND"}


def test_api_feedback_repeated_call_is_200(repo):
    lead = _seed_lead(repo)
    client = _client(repo)
    payload = {"lead_id": str(lead.id), "kind": "unsubscribe"}

    first = client.post(
        "/internal/v1/social/feedback",
        json=payload,
        headers={"X-Service-Token": SERVICE_TOKEN},
    )
    second = client.post(
        "/internal/v1/social/feedback",
        json=payload,
        headers={"X-Service-Token": SERVICE_TOKEN},
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["status"] == second.json()["status"] == "suppressed"


def test_api_feedback_requires_service_token(repo):
    response = _client(repo).post(
        "/internal/v1/social/feedback",
        json={"lead_id": str(uuid4()), "kind": "replied"},
    )

    assert response.status_code == 401
