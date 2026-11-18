"""Tests for manual send tracking and send-time rate limits.

"Sent" is always a human-recorded action: :func:`mark_sent` only moves database
state, writes an audit row, and schedules the follow-up check. It never talks
to a platform, a notifier, or Feishu.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from growth_core.config import GrowthSettings
from growth_core.schemas import (
    NewApprovalRequest,
    NewOutreachVersion,
    OutreachMessage,
    RateLimitRule,
    SocialLead,
)
from growth_core.services.ratelimit import RateLimitContext, check_send_allowed
from growth_social.main import create_social_app
from growth_social.services.sending import SendBlocked, mark_sent

CLOCK = datetime(2026, 11, 15, 9, 0, tzinfo=timezone.utc)
WINDOW = 86400

TENANT = UUID("00000000-0000-0000-0000-000000000001")
WORKSPACE = UUID("00000000-0000-0000-0000-000000000002")
SERVICE_TOKEN = "service-token"


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
        "feishu_verification_token": "verify-token",
    }
    values.update(overrides)
    return GrowthSettings(**values)


def _client(repo) -> TestClient:
    return TestClient(create_social_app(settings=_settings(), repo=repo))


def _run(coro):
    return asyncio.run(coro)


def _window_start(now: datetime, window_seconds: int = WINDOW) -> datetime:
    return now - timedelta(seconds=int(now.timestamp()) % window_seconds)


def _seed_rules(
    repo,
    *,
    global_max: int = 50,
    reddit_max: int = 5,
    subreddit_max: int = 2,
    enabled: bool = True,
    include_global: bool = True,
) -> None:
    rules = [
        ("platform", "reddit", reddit_max),
        ("subreddit", "*", subreddit_max),
    ]
    if include_global:
        rules.insert(0, ("global", "*", global_max))
    for scope, scope_key, max_count in rules:
        repo.rate_rules[(TENANT, "social", scope, scope_key)] = RateLimitRule(
            tenant_id=TENANT,
            channel="social",
            scope=scope,
            scope_key=scope_key,
            window_seconds=WINDOW,
            max_count=max_count,
            enabled=enabled,
        )


def _seed_lead(
    repo,
    *,
    status: str = "qualified",
    platform: str = "reddit",
    subreddit: str | None = "SaaS",
    author_public: str | None = "alice",
) -> SocialLead:
    lead = SocialLead(
        id=uuid4(),
        tenant_id=TENANT,
        workspace_id=WORKSPACE,
        platform=platform,
        platform_post_id=str(uuid4()),
        title="How do you keep onboarding emails personal?",
        body="Our welcome sequence feels generic after 200 signups.",
        author_public=author_public,
        source_url="https://reddit.example/r/SaaS/post/1",
        subreddit=subreddit,
        dedupe_key=str(uuid4()),
        status=status,
        created_at=CLOCK,
        updated_at=CLOCK,
    )
    repo.leads.append(lead)
    return lead


def _seed_message(
    repo,
    lead: SocialLead,
    *,
    status: str = "approved",
    metadata: dict | None = None,
) -> OutreachMessage:
    message = OutreachMessage(
        id=uuid4(),
        tenant_id=TENANT,
        workspace_id=WORKSPACE,
        channel="social",
        provider=lead.platform,
        lead_id=lead.id,
        status=status,
        dedupe_key=f"draft:{uuid4()}",
        metadata={} if metadata is None else metadata,
        created_at=CLOCK,
        updated_at=CLOCK,
    )
    repo.messages.append(message)
    return message


async def _seed_version(repo, message: OutreachMessage) -> None:
    await repo.create_version(
        NewOutreachVersion(
            tenant_id=TENANT,
            message_id=message.id,
            version=1,
            body_text="A helpful reply with exactly one link.",
            cta_url="https://example.com",
        )
    )


async def _seed_approval(repo, message: OutreachMessage):
    return await repo.create_approval_request(
        NewApprovalRequest(
            tenant_id=TENANT,
            workspace_id=WORKSPACE,
            message_id=message.id,
            approval_id=f"{message.id}:v1",
            provider="feishu",
        )
    )


def _send(repo, message: OutreachMessage, **kwargs):
    return mark_sent(
        repo,
        tenant_id=TENANT,
        workspace_id=WORKSPACE,
        message_id=message.id,
        now=CLOCK,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# check_send_allowed
# ---------------------------------------------------------------------------


async def test_check_send_allowed_fails_closed_without_global_rule(repo):
    _seed_rules(repo, include_global=False)

    decision = await check_send_allowed(
        repo,
        RateLimitContext(
            tenant_id=TENANT,
            channel="social",
            platform="reddit",
            subreddit="SaaS",
            has_link=True,
            now=CLOCK,
        ),
    )

    assert decision.allowed is False
    assert decision.exceeded_scope == "global"
    assert decision.exceeded_scope_key == "*"


async def test_check_send_allowed_skips_disabled_rules(repo):
    _seed_rules(repo, enabled=False)

    decision = await check_send_allowed(
        repo,
        RateLimitContext(
            tenant_id=TENANT,
            channel="social",
            platform="reddit",
            subreddit="SaaS",
            has_link=True,
            now=CLOCK,
        ),
    )

    assert decision.allowed is False
    assert decision.exceeded_scope == "global"


# ---------------------------------------------------------------------------
# mark_sent: state transition and follow-up scheduling
# ---------------------------------------------------------------------------


async def test_mark_sent_transitions_and_schedules_followup(repo):
    _seed_rules(repo)
    lead = _seed_lead(repo)
    message = _seed_message(repo, lead)
    await _seed_version(repo, message)

    updated = await _send(repo, message)

    assert updated.status == "sent"
    assert updated.sent_at == CLOCK
    tasks = repo.tasks_for(f"followup:{message.id}")
    assert len(tasks) == 1
    assert tasks[0].task_type == "social.followup_check"
    assert tasks[0].payload == {"original_message_id": str(message.id)}
    assert tasks[0].run_after == CLOCK + timedelta(days=1)


async def test_mark_sent_stamps_send_metadata(repo):
    _seed_rules(repo)
    lead = _seed_lead(repo)
    message = _seed_message(repo, lead)
    await _seed_version(repo, message)

    updated = await _send(repo, message, channel="manual")

    assert updated.metadata["channel"] == "manual"
    assert updated.metadata["subreddit"] == "SaaS"
    assert updated.metadata["has_link"] is True
    assert updated.metadata["draft_version"] == 1
    assert updated.provider == "reddit"


async def test_mark_sent_expires_pending_approvals(repo):
    _seed_rules(repo)
    lead = _seed_lead(repo)
    message = _seed_message(repo, lead)
    await _seed_version(repo, message)
    await _seed_approval(repo, message)

    await _send(repo, message)

    assert [approval.status for approval in repo.approvals] == ["expired"]


async def test_mark_sent_records_delivery_and_audit(repo):
    _seed_rules(repo)
    lead = _seed_lead(repo)
    message = _seed_message(repo, lead)
    await _seed_version(repo, message)

    await _send(repo, message)

    assert len(repo.deliveries) == 1
    delivery = repo.deliveries[0]
    assert delivery["event_type"] == "sent"
    assert delivery["provider"] == "reddit"
    assert delivery["message_id"] == message.id
    assert delivery["payload"] == {"channel": "manual"}

    actions = [entry["action"] for entry in repo.audit]
    assert "social.sent" in actions


async def test_mark_sent_uses_explicit_sent_at_for_followup(repo):
    _seed_rules(repo)
    lead = _seed_lead(repo)
    message = _seed_message(repo, lead)
    await _seed_version(repo, message)
    sent_at = CLOCK - timedelta(hours=2)

    updated = await mark_sent(
        repo,
        tenant_id=TENANT,
        workspace_id=WORKSPACE,
        message_id=message.id,
        sent_at=sent_at,
    )

    assert updated.sent_at == sent_at
    assert repo.tasks_for(f"followup:{message.id}")[0].run_after == (
        sent_at + timedelta(days=1)
    )


# ---------------------------------------------------------------------------
# mark_sent: transition and lead-state gates
# ---------------------------------------------------------------------------


async def test_mark_sent_requires_approved_status(repo):
    _seed_rules(repo)
    lead = _seed_lead(repo)
    message = _seed_message(repo, lead, status="draft_ready")

    with pytest.raises(SendBlocked, match="INVALID_TRANSITION"):
        await _send(repo, message)


async def test_mark_sent_missing_message(repo):
    with pytest.raises(SendBlocked, match="NOT_FOUND"):
        await mark_sent(
            repo,
            tenant_id=TENANT,
            workspace_id=WORKSPACE,
            message_id=uuid4(),
            now=CLOCK,
        )


async def test_mark_sent_missing_lead(repo):
    message = OutreachMessage(
        id=uuid4(),
        tenant_id=TENANT,
        workspace_id=WORKSPACE,
        channel="social",
        provider="reddit",
        lead_id=uuid4(),
        status="approved",
        dedupe_key=str(uuid4()),
        created_at=CLOCK,
        updated_at=CLOCK,
    )
    repo.messages.append(message)

    with pytest.raises(SendBlocked, match="NOT_FOUND"):
        await _send(repo, message)


async def test_mark_sent_blocks_original_when_lead_already_contacted(repo):
    _seed_rules(repo)
    lead = _seed_lead(repo, status="replied")
    message = _seed_message(repo, lead)

    with pytest.raises(SendBlocked, match="ALREADY_CONTACTED"):
        await _send(repo, message)


@pytest.mark.parametrize("status", ["suppressed", "rejected"])
async def test_mark_sent_blocks_original_when_lead_closed(repo, status):
    _seed_rules(repo)
    lead = _seed_lead(repo, status=status)
    message = _seed_message(repo, lead)

    with pytest.raises(SendBlocked, match="LEAD_CLOSED"):
        await _send(repo, message)


async def test_mark_sent_blocks_followup_when_lead_closed(repo):
    _seed_rules(repo)
    lead = _seed_lead(repo, status="converted")
    message = _seed_message(
        repo, lead, metadata={"followup_of": str(uuid4())}
    )

    with pytest.raises(SendBlocked, match="LEAD_CLOSED"):
        await _send(repo, message)


async def test_mark_sent_allows_followup_while_lead_is_sent(repo):
    _seed_rules(repo)
    lead = _seed_lead(repo, status="sent")
    original_id = uuid4()
    message = _seed_message(
        repo, lead, metadata={"followup_of": str(original_id)}
    )
    await _seed_version(repo, message)

    updated = await _send(repo, message)

    assert updated.status == "sent"
    tasks = repo.tasks_for(f"followup:{original_id}")
    assert len(tasks) == 1
    assert tasks[0].idempotency_key == f"followup:{original_id}:{message.id}"


async def test_mark_sent_blocks_second_original_for_same_author(repo):
    _seed_rules(repo)
    first_lead = _seed_lead(repo)
    first_message = _seed_message(repo, first_lead)
    await _seed_version(repo, first_message)
    await _send(repo, first_message)

    second_lead = _seed_lead(repo)
    second_message = _seed_message(repo, second_lead)

    with pytest.raises(SendBlocked, match="ALREADY_CONTACTED_USER"):
        await _send(repo, second_message)

    stored = await repo.get_message(TENANT, second_message.id)
    assert stored.status == "suppressed"
    blocked = [
        entry
        for entry in repo.audit
        if entry["action"] == "social.send_blocked"
        and entry["after"].get("scope") == "author"
    ]
    assert len(blocked) == 1
    assert blocked[0]["entity_id"] == second_message.id


async def test_mark_sent_allows_followup_for_same_author(repo):
    _seed_rules(repo)
    first_lead = _seed_lead(repo)
    first_message = _seed_message(repo, first_lead)
    await _seed_version(repo, first_message)
    await _send(repo, first_message)

    second_lead = _seed_lead(repo)
    followup = _seed_message(
        repo,
        second_lead,
        metadata={"followup_of": str(first_message.id)},
    )
    await _seed_version(repo, followup)

    updated = await _send(repo, followup)

    assert updated.status == "sent"


async def test_mark_sent_allows_original_for_different_author(repo):
    _seed_rules(repo)
    first_lead = _seed_lead(repo)
    first_message = _seed_message(repo, first_lead)
    await _seed_version(repo, first_message)
    await _send(repo, first_message)

    other_lead = _seed_lead(repo, author_public="bob")
    other_message = _seed_message(repo, other_lead)
    await _seed_version(repo, other_message)

    updated = await _send(repo, other_message)

    assert updated.status == "sent"


@pytest.mark.parametrize("author_public", ["[deleted]", ""])
async def test_mark_sent_skips_same_author_check_for_deleted_users(
    repo, author_public
):
    _seed_rules(repo)
    first_lead = _seed_lead(repo, author_public=author_public)
    first_message = _seed_message(repo, first_lead)
    await _seed_version(repo, first_message)
    await _send(repo, first_message)

    # All deleted users share this value, so it must not block another lead.
    second_lead = _seed_lead(repo, author_public=author_public)
    second_message = _seed_message(repo, second_lead)
    await _seed_version(repo, second_message)

    updated = await _send(repo, second_message)

    assert updated.status == "sent"


async def test_mark_sent_ignores_suppression_keyed_on_deleted_author(repo):
    _seed_rules(repo)
    lead = _seed_lead(repo, author_public="[deleted]")
    message = _seed_message(repo, lead)
    await _seed_version(repo, message)
    await repo.add_suppression(
        TENANT, "platform_user", f"{lead.platform}:{lead.author_public}", "manual"
    )

    updated = await _send(repo, message)

    assert updated.status == "sent"


async def test_mark_sent_raises_concurrent_update(repo, monkeypatch):
    _seed_rules(repo)
    lead = _seed_lead(repo)
    message = _seed_message(repo, lead)
    await _seed_version(repo, message)

    async def _lost_cas(*args, **kwargs):
        return False

    monkeypatch.setattr(repo, "update_message_status", _lost_cas)

    with pytest.raises(SendBlocked, match="CONCURRENT_UPDATE"):
        await _send(repo, message)


# ---------------------------------------------------------------------------
# mark_sent: suppression and rate limits
# ---------------------------------------------------------------------------


async def test_mark_sent_blocks_suppressed_platform_user(repo):
    _seed_rules(repo)
    lead = _seed_lead(repo)
    message = _seed_message(repo, lead)
    await repo.add_suppression(
        TENANT, "platform_user", f"{lead.platform}:{lead.author_public}", "manual"
    )

    with pytest.raises(SendBlocked, match="SUPPRESSED"):
        await _send(repo, message)

    stored = await repo.get_message(TENANT, message.id)
    assert stored.status == "suppressed"
    assert any(
        entry["action"] == "social.send_suppressed" for entry in repo.audit
    )


async def test_mark_sent_blocks_reddit_daily_limit(repo):
    _seed_rules(repo)
    lead = _seed_lead(repo)
    message = _seed_message(repo, lead)
    repo.set_rate_counter(
        TENANT, "social", "platform", "reddit", _window_start(CLOCK), 5
    )

    with pytest.raises(SendBlocked, match="RATE_LIMITED"):
        await _send(repo, message)

    stored = await repo.get_message(TENANT, message.id)
    assert stored.status == "suppressed"
    blocked = [
        entry for entry in repo.audit if entry["action"] == "social.send_blocked"
    ]
    assert blocked[0]["after"]["scope"] == "platform"
    assert blocked[0]["after"]["scope_key"] == "reddit"


async def test_mark_sent_blocks_global_daily_limit(repo):
    _seed_rules(repo)
    lead = _seed_lead(repo)
    message = _seed_message(repo, lead)
    repo.set_rate_counter(
        TENANT, "social", "global", "*", _window_start(CLOCK), 50
    )

    with pytest.raises(SendBlocked, match="RATE_LIMITED"):
        await _send(repo, message)

    stored = await repo.get_message(TENANT, message.id)
    assert stored.status == "suppressed"


async def test_mark_sent_blocks_subreddit_link_limit(repo):
    _seed_rules(repo)
    lead = _seed_lead(repo)
    message = _seed_message(repo, lead)
    repo.set_rate_counter(
        TENANT, "social", "subreddit", "SaaS", _window_start(CLOCK), 2
    )

    with pytest.raises(SendBlocked, match="RATE_LIMITED"):
        await _send(repo, message)

    stored = await repo.get_message(TENANT, message.id)
    assert stored.status == "suppressed"


async def test_mark_sent_skips_subreddit_check_without_link(repo):
    # ``mark_sent`` always sends with ``has_link=True``; call the policy
    # directly to prove link-less replies do not consume a subreddit rule.
    _seed_rules(repo)
    repo.set_rate_counter(
        TENANT, "social", "subreddit", "SaaS", _window_start(CLOCK), 2
    )

    decision = await check_send_allowed(
        repo,
        RateLimitContext(
            tenant_id=TENANT,
            channel="social",
            platform="reddit",
            subreddit="SaaS",
            has_link=False,
            now=CLOCK,
        ),
    )

    assert decision.allowed is True


# ---------------------------------------------------------------------------
# HTTP endpoint
# ---------------------------------------------------------------------------


def test_api_mark_sent_happy_path(repo):
    _seed_rules(repo)

    async def seed():
        lead = _seed_lead(repo)
        message = _seed_message(repo, lead)
        await _seed_version(repo, message)
        return message

    message = _run(seed())

    response = _client(repo).post(
        f"/api/growth/social/messages/{message.id}/sent",
        json={
            "sent_at": CLOCK.isoformat(),
            "channel": "manual",
            "operator": "operator-1",
        },
        headers={"X-Service-Token": SERVICE_TOKEN},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["message_id"] == str(message.id)
    assert body["status"] == "sent"
    assert body["channel"] == "manual"
    assert datetime.fromisoformat(body["sent_at"]) == CLOCK
    sent_audits = [
        entry for entry in repo.audit if entry["action"] == "social.sent"
    ]
    assert len(sent_audits) == 1
    assert sent_audits[0]["actor_type"] == "user"
    assert sent_audits[0]["actor_id"] == "operator-1"


def test_api_mark_sent_operator_defaults_to_none(repo):
    _seed_rules(repo)

    async def seed():
        lead = _seed_lead(repo)
        message = _seed_message(repo, lead)
        await _seed_version(repo, message)
        return message

    message = _run(seed())

    response = _client(repo).post(
        f"/api/growth/social/messages/{message.id}/sent",
        json={},
        headers={"X-Service-Token": SERVICE_TOKEN},
    )

    assert response.status_code == 200
    sent_audits = [
        entry for entry in repo.audit if entry["action"] == "social.sent"
    ]
    assert sent_audits[0]["actor_id"] is None


def test_api_mark_sent_invalid_transition(repo):
    _seed_rules(repo)

    async def seed():
        lead = _seed_lead(repo)
        return _seed_message(repo, lead, status="draft_ready")

    message = _run(seed())

    response = _client(repo).post(
        f"/api/growth/social/messages/{message.id}/sent",
        json={},
        headers={"X-Service-Token": SERVICE_TOKEN},
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "INVALID_TRANSITION"


def test_api_mark_sent_missing_message(repo):
    message_id = uuid4()

    response = _client(repo).post(
        f"/api/growth/social/messages/{message_id}/sent",
        json={},
        headers={"X-Service-Token": SERVICE_TOKEN},
    )

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "NOT_FOUND"


def test_api_mark_sent_requires_service_token(repo):
    message_id = uuid4()

    response = _client(repo).post(
        f"/api/growth/social/messages/{message_id}/sent", json={}
    )

    assert response.status_code == 401
