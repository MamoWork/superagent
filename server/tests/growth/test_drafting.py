"""Tests for reply drafting, approval cards, and retry idempotency."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest

from growth_core import seed_data
from growth_core.adapters.base import ProviderNotConfigured, ProviderUnavailable
from growth_core.config import GrowthSettings
from growth_core.services.outbox import dispatch_outbox
from growth_core.schemas import (
    NewOutreachMessage,
    NewOutreachVersion,
    OutreachMessage,
    PromptTemplate,
    SocialLead,
)
from growth_social.schemas import ReplyDraft
from growth_social.services.drafting import draft_reply
from tests.growth.fakes import FakeGrowthRepository, FakeNotifier

CLOCK = datetime(2026, 11, 15, 9, 0, tzinfo=timezone.utc)

VALID_BODY = (
    "That onboarding slog sounds painful. I built Example, and this checklist "
    "helps: {{LINK}}"
)


class FakeLLM:
    """Deterministic LLM double that records every call."""

    model = "fake-drafter"

    def __init__(self, draft: ReplyDraft | None = None, *, exc=None) -> None:
        self.draft = draft
        self.exc = exc
        self.calls: list[dict] = []

    async def complete_json(self, *, system, user, schema, model=None):
        self.calls.append(
            {"system": system, "user": user, "schema": schema, "model": model}
        )
        if self.exc is not None:
            raise self.exc
        assert self.draft is not None
        return self.draft


def _valid_draft(**overrides) -> ReplyDraft:
    data = {
        "body_markdown": VALID_BODY,
        "link_path": "/guides/churn",
        "risk_flags": ["no_promises"],
    }
    data.update(overrides)
    return ReplyDraft(**data)


def _prompt(tenant_id: UUID, version: int = 3) -> PromptTemplate:
    return PromptTemplate(
        id=uuid4(),
        tenant_id=tenant_id,
        key="social_reply",
        module="social",
        version=version,
        template=seed_data.SOCIAL_REPLY_SYSTEM,
        user_template=seed_data.SOCIAL_REPLY_USER,
        output_schema={"type": "object"},
        enabled=True,
    )


def _settings(
    tenant_id: UUID, workspace_id: UUID, **overrides
) -> GrowthSettings:
    values = {
        "database_url": "postgres://test",
        "service_token": "token",
        "tenant_id": str(tenant_id),
        "workspace_id": str(workspace_id),
        "feishu_chat_id": "oc_chat",
        "product_url": "https://example.com",
        "product_domain": "example.com",
        "llm_drafting_model": "drafter-v1",
    }
    values.update(overrides)
    return GrowthSettings(**values)


def _make_lead(
    tenant_id: UUID,
    workspace_id: UUID,
    *,
    now: datetime = CLOCK,
    **overrides,
) -> SocialLead:
    data = {
        "id": uuid4(),
        "tenant_id": tenant_id,
        "workspace_id": workspace_id,
        "platform": "reddit",
        "platform_post_id": str(uuid4()),
        "title": "How do you keep onboarding emails personal?",
        "body": "Our welcome sequence feels generic after 200 signups.",
        "source_url": "https://reddit.example/r/SaaS/post/1",
        "subreddit": "SaaS",
        "subreddit_rules": {"self_promotion_allowed": True},
        "dedupe_key": str(uuid4()),
        "status": "qualified",
        "score": 91,
        "created_at": now,
        "updated_at": now,
    }
    data.update(overrides)
    return SocialLead(**data)


def _add_lead(
    repo: FakeGrowthRepository,
    tenant_id: UUID,
    workspace_id: UUID,
    **overrides,
) -> SocialLead:
    lead = _make_lead(tenant_id, workspace_id, **overrides)
    repo.leads.append(lead.model_copy(deep=True))
    return lead


def _seed(
    repo: FakeGrowthRepository,
    tenant_id: UUID,
    workspace_id: UUID,
    **lead_overrides,
):
    repo.prompts[(tenant_id, "social_reply", 3)] = _prompt(tenant_id)
    lead = _add_lead(repo, tenant_id, workspace_id, **lead_overrides)
    return lead


def _expected_url(lead: SocialLead) -> str:
    return (
        "https://example.com/guides/churn"
        f"?utm_source=reddit&utm_medium=reply&utm_campaign={lead.id}"
    )


async def _draft(
    repo: FakeGrowthRepository,
    llm: FakeLLM,
    notifier: FakeNotifier,
    tenant_id: UUID,
    workspace_id: UUID,
    lead,
    settings: GrowthSettings,
    now: datetime = CLOCK,
) -> OutreachMessage:
    return await draft_reply(
        repo,
        llm,
        notifier,
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        lead_id=lead.id,
        settings=settings,
        now=now,
    )


def _outbox_key(approval_id: str) -> str:
    return f"feishu:{approval_id}"


# ---------------------------------------------------------------------------
# Success path
# ---------------------------------------------------------------------------


async def test_card_uses_platform_publish_time_when_available(repo, now):
    tenant, workspace = uuid4(), uuid4()
    published_at = now - timedelta(hours=6)
    lead = _seed(repo, tenant, workspace, published_at=published_at)

    await _draft(
        repo,
        FakeLLM(_valid_draft()),
        FakeNotifier(),
        tenant,
        workspace,
        lead,
        _settings(tenant, workspace),
        now,
    )

    card = repo.outbox[0].payload["card"]
    published_element = next(
        element
        for element in card["elements"]
        if element.get("text", {}).get("content", "").startswith("发布时间:")
    )
    assert published_at.isoformat() in published_element["text"]["content"]


async def test_success_creates_message_version_approval_outbox_card_and_audit(
    repo, now
):
    tenant, workspace = uuid4(), uuid4()
    lead = _seed(repo, tenant, workspace)
    llm = FakeLLM(_valid_draft())
    notifier = FakeNotifier()
    settings = _settings(tenant, workspace)
    expected_url = _expected_url(lead)

    message = await _draft(
        repo, llm, notifier, tenant, workspace, lead, settings, now
    )

    # Message ---------------------------------------------------------
    assert message.status == "draft_ready"
    assert message.channel == "social"
    assert message.provider == "reddit"
    assert message.lead_id == lead.id
    assert message.workspace_id == workspace
    assert message.dedupe_key == f"draft:{lead.id}"
    assert message.metadata == {
        "subreddit": "SaaS",
        "has_link": True,
        "platform": "reddit",
        "draft_version": 1,
    }
    assert len(repo.messages) == 1

    # Version ---------------------------------------------------------
    version = await repo.get_latest_version(tenant, message.id)
    assert version is not None
    assert version.tenant_id == tenant
    assert version.message_id == message.id
    assert version.version == 1
    assert version.body_text == VALID_BODY.replace("{{LINK}}", expected_url)
    assert version.cta_url == expected_url
    assert version.model == "drafter-v1"
    assert version.prompt_version == "3"
    assert version.risk_flags == ["no_promises"]
    assert len(repo.outreach_versions) == 1

    # Approval --------------------------------------------------------
    approval_id = f"{message.id}:v1"
    approval = await repo.get_approval_request(tenant, approval_id)
    assert approval is not None
    assert approval.workspace_id == workspace
    assert approval.message_id == message.id
    assert approval.provider == "feishu"
    assert approval.payload == {"chat_id": "oc_chat"}
    assert approval.status == "pending"
    assert len(repo.approvals) == 1

    # Outbox ----------------------------------------------------------
    rows = repo.outbox_for(_outbox_key(approval_id))
    assert len(rows) == 1
    row = rows[0]
    assert row.tenant_id == tenant
    assert row.workspace_id == workspace
    assert row.topic == "feishu.card"
    assert row.payload["chat_id"] == "oc_chat"
    assert row.payload["approval_id"] == approval_id
    assert notifier.cards == []

    # Card (built into the outbox row, not delivered by drafting) ------
    card = row.payload["card"]
    assert card["config"]["wide_screen_mode"] is True
    assert card["header"]["title"]["content"] == "Social reply approval"
    serialized = json.dumps(card)
    assert lead.title in serialized
    assert lead.source_url in serialized
    assert "SaaS" in serialized
    assert "91" in serialized
    assert "no_promises" in serialized
    assert expected_url in serialized
    assert "SECRET" not in serialized
    published_element = next(
        element
        for element in card["elements"]
        if element.get("text", {}).get("content", "").startswith("发布时间:")
    )
    assert published_element["text"]["tag"] == "plain_text"
    # The lead has no platform ``published_at`` in this fixture, so the card
    # falls back to the lead row's ``created_at``.
    assert lead.created_at.isoformat() in published_element["text"]["content"]
    assert card["elements"][-1]["text"]["content"].find(expected_url) != -1
    actions = next(
        element for element in card["elements"] if element.get("tag") == "action"
    )
    assert [button["value"] for button in actions["actions"]] == [
        {"approval_id": approval_id, "action": "approve"},
        {"approval_id": approval_id, "action": "edit"},
        {"approval_id": approval_id, "action": "reject"},
        {"approval_id": approval_id, "action": "later"},
    ]
    title_element = next(
        element
        for element in card["elements"]
        if lead.title in element.get("text", {}).get("content", "")
    )
    assert title_element["text"]["tag"] == "plain_text"

    # Delivery is the worker/outbox dispatcher's job.
    sent = await dispatch_outbox(repo, notifier, now=now)
    assert sent == 1
    assert len(notifier.cards) == 1
    assert notifier.cards[0] == card

    # Audit -----------------------------------------------------------
    created = [a for a in repo.audit if a["action"] == "social.draft_created"]
    assert len(created) == 1
    entry = created[0]
    assert entry["tenant_id"] == tenant
    assert entry["workspace_id"] == workspace
    assert entry["actor_type"] == "service"
    assert entry["entity_type"] == "outreach_message"
    assert entry["entity_id"] == message.id
    assert entry["after"] == {
        "approval_id": approval_id,
        "draft_version": 1,
    }

    # Lead ------------------------------------------------------------
    stored = await repo.get_lead(tenant, lead.id)
    assert stored is not None
    assert stored.status == "draft_ready"


async def test_success_renders_prompt_and_uses_drafting_model(repo, now):
    tenant, workspace = uuid4(), uuid4()
    lead = _seed(repo, tenant, workspace)
    llm = FakeLLM(_valid_draft())
    settings = _settings(tenant, workspace)

    await _draft(
        repo, llm, FakeNotifier(), tenant, workspace, lead, settings, now
    )

    assert len(llm.calls) == 1
    call = llm.calls[0]
    assert call["system"] == seed_data.SOCIAL_REPLY_SYSTEM
    assert call["schema"] is ReplyDraft
    assert call["model"] == "drafter-v1"
    assert call["user"] == (
        "Platform: reddit\n"
        "Community: SaaS\n"
        "Title: How do you keep onboarding emails personal?\n"
        "Body:\n"
        "Our welcome sequence feels generic after 200 signups.\n"
        "Product: example.com\n"
        "Product site: https://example.com\n"
    )


async def test_configured_product_name_is_used_in_prompt(repo, now):
    tenant, workspace = uuid4(), uuid4()
    lead = _seed(repo, tenant, workspace)
    llm = FakeLLM(_valid_draft())
    settings = _settings(tenant, workspace, product_name="Example App")

    await _draft(
        repo, llm, FakeNotifier(), tenant, workspace, lead, settings, now
    )

    assert "Product: Example App\n" in llm.calls[0]["user"]


async def test_community_falls_back_to_platform(repo, now):
    tenant, workspace = uuid4(), uuid4()
    lead = _seed(repo, tenant, workspace, platform="hackernews", subreddit=None)
    llm = FakeLLM(
        _valid_draft(
            body_markdown=(
                "That onboarding slog sounds painful. I built Example, and this "
                "checklist helps: {{LINK}}"
            )
        )
    )

    await _draft(
        repo,
        llm,
        FakeNotifier(),
        tenant,
        workspace,
        lead,
        _settings(tenant, workspace),
        now,
    )

    assert "Community: hackernews\n" in llm.calls[0]["user"]


async def test_version_model_falls_back_to_llm_attribute(repo, now):
    tenant, workspace = uuid4(), uuid4()
    lead = _seed(repo, tenant, workspace)
    llm = FakeLLM(_valid_draft())
    settings = _settings(tenant, workspace, llm_drafting_model="")

    message = await _draft(
        repo, llm, FakeNotifier(), tenant, workspace, lead, settings, now
    )

    version = await repo.get_latest_version(tenant, message.id)
    assert version is not None
    assert version.model == "fake-drafter"
    assert llm.calls[0]["model"] is None


# ---------------------------------------------------------------------------
# Rejection and suppression
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "body",
    [
        "I built Example, and this checklist helps.",
        "I built Example, and this helps: {{LINK}} or {{LINK}}.",
    ],
    ids=["missing-placeholder", "two-placeholders"],
)
async def test_placeholder_count_is_rejected(repo, now, body):
    tenant, workspace = uuid4(), uuid4()
    lead = _seed(repo, tenant, workspace)
    llm = FakeLLM(_valid_draft(body_markdown=body))
    notifier = FakeNotifier()

    message = await _draft(
        repo,
        llm,
        notifier,
        tenant,
        workspace,
        lead,
        _settings(tenant, workspace),
        now,
    )

    assert message.status == "rejected"
    assert message.dedupe_key == f"draft:{lead.id}"
    assert message.metadata == {"policy_violations": ["PLACEHOLDER_COUNT"]}
    assert repo.outreach_versions == []
    assert repo.approvals == []
    assert repo.outbox == []
    assert await dispatch_outbox(repo, notifier, now=now) == 0
    assert notifier.cards == []
    rejected = [a for a in repo.audit if a["action"] == "social.draft_rejected"]
    assert len(rejected) == 1
    assert rejected[0]["after"] == {"policy_violations": ["PLACEHOLDER_COUNT"]}
    stored = await repo.get_lead(tenant, lead.id)
    assert stored is not None and stored.status == "qualified"


async def test_subreddit_without_links_is_suppressed(repo, now):
    tenant, workspace = uuid4(), uuid4()
    lead = _seed(
        repo,
        tenant,
        workspace,
        subreddit_rules={"self_promotion_allowed": False},
    )
    llm = FakeLLM(_valid_draft())
    notifier = FakeNotifier()

    message = await _draft(
        repo,
        llm,
        notifier,
        tenant,
        workspace,
        lead,
        _settings(tenant, workspace),
        now,
    )

    assert message.status == "suppressed"
    assert message.metadata["policy_violations"] == ["SUBREDDIT_NO_LINKS"]
    assert repo.outreach_versions == []
    assert repo.approvals == []
    assert repo.outbox == []
    assert await dispatch_outbox(repo, notifier, now=now) == 0
    assert notifier.cards == []
    suppressed = [
        a for a in repo.audit if a["action"] == "social.draft_suppressed"
    ]
    assert len(suppressed) == 1
    assert suppressed[0]["after"] == {
        "policy_violations": ["SUBREDDIT_NO_LINKS"]
    }


@pytest.mark.parametrize("rule_value", [None, 0], ids=["none", "zero"])
async def test_falsey_subreddit_rule_suppresses_links(repo, now, rule_value):
    tenant, workspace = uuid4(), uuid4()
    lead = _seed(
        repo,
        tenant,
        workspace,
        subreddit_rules={"self_promotion_allowed": rule_value},
    )

    message = await _draft(
        repo,
        FakeLLM(_valid_draft()),
        FakeNotifier(),
        tenant,
        workspace,
        lead,
        _settings(tenant, workspace),
        now,
    )

    assert message.status == "suppressed"
    assert "SUBREDDIT_NO_LINKS" in message.metadata["policy_violations"]


async def test_explicit_true_subreddit_rule_allows_links(repo, now):
    tenant, workspace = uuid4(), uuid4()
    lead = _seed(
        repo, tenant, workspace, subreddit_rules={"self_promotion_allowed": True}
    )

    message = await _draft(
        repo,
        FakeLLM(_valid_draft()),
        FakeNotifier(),
        tenant,
        workspace,
        lead,
        _settings(tenant, workspace),
        now,
    )

    assert message.status == "draft_ready"


async def test_missing_subreddit_rules_fail_closed(repo, now):
    tenant, workspace = uuid4(), uuid4()
    lead = _seed(repo, tenant, workspace, subreddit_rules={})

    message = await _draft(
        repo,
        FakeLLM(_valid_draft()),
        FakeNotifier(),
        tenant,
        workspace,
        lead,
        _settings(tenant, workspace),
        now,
    )

    assert message.status == "suppressed"
    assert "SUBREDDIT_NO_LINKS" in message.metadata["policy_violations"]
    assert repo.outbox == []


async def test_llm_policy_violation_is_rejected(repo, now):
    tenant, workspace = uuid4(), uuid4()
    lead = _seed(repo, tenant, workspace)
    llm = FakeLLM(_valid_draft())
    notifier = FakeNotifier()
    # The configured site is on a domain the policy does not allow.
    settings = _settings(
        tenant, workspace, product_url="https://other.example"
    )

    message = await _draft(
        repo, llm, notifier, tenant, workspace, lead, settings, now
    )

    assert message.status == "rejected"
    assert message.metadata["policy_violations"] == ["WRONG_DOMAIN"]
    assert repo.outreach_versions == []
    assert repo.approvals == []
    assert repo.outbox == []
    assert await dispatch_outbox(repo, notifier, now=now) == 0
    assert notifier.cards == []
    rejected = [a for a in repo.audit if a["action"] == "social.draft_rejected"]
    assert len(rejected) == 1
    assert rejected[0]["after"] == {"policy_violations": ["WRONG_DOMAIN"]}


# ---------------------------------------------------------------------------
# Retry idempotency
# ---------------------------------------------------------------------------


async def test_retry_after_success_creates_no_duplicates(repo, now):
    tenant, workspace = uuid4(), uuid4()
    lead = _seed(repo, tenant, workspace)
    llm = FakeLLM(_valid_draft())
    notifier = FakeNotifier()
    settings = _settings(tenant, workspace)

    first = await _draft(
        repo, llm, notifier, tenant, workspace, lead, settings, now
    )
    assert await dispatch_outbox(repo, notifier, now=now) == 1
    assert len(notifier.cards) == 1
    audit_count = len(repo.audit)
    llm.exc = AssertionError("retry must not call the LLM")

    second = await _draft(
        repo, llm, notifier, tenant, workspace, lead, settings, now
    )
    assert await dispatch_outbox(repo, notifier, now=now) == 0

    assert second.id == first.id
    assert len(llm.calls) == 1
    assert len(repo.messages) == 1
    assert len(repo.outreach_versions) == 1
    assert len(repo.approvals) == 1
    assert len(repo.outbox) == 1
    assert len(notifier.cards) == 1
    assert len(repo.audit) == audit_count


async def test_retry_after_success_resends_card_when_outbox_row_is_missing(
    repo, now
):
    tenant, workspace = uuid4(), uuid4()
    lead = _seed(repo, tenant, workspace)
    llm = FakeLLM(_valid_draft())
    notifier = FakeNotifier()
    settings = _settings(tenant, workspace)

    first = await _draft(
        repo, llm, notifier, tenant, workspace, lead, settings, now
    )
    assert await dispatch_outbox(repo, notifier, now=now) == 1
    assert len(notifier.cards) == 1
    repo.outbox.clear()
    llm.exc = AssertionError("retry must not call the LLM")

    second = await _draft(
        repo, llm, notifier, tenant, workspace, lead, settings, now
    )

    assert second.id == first.id
    assert len(llm.calls) == 1
    assert len(repo.messages) == 1
    assert len(repo.outreach_versions) == 1
    assert len(repo.approvals) == 1
    assert len(repo.outbox) == 1
    assert await dispatch_outbox(repo, notifier, now=now) == 1
    assert len(notifier.cards) == 2


async def test_crash_window_without_version_returns_existing(repo, now):
    tenant, workspace = uuid4(), uuid4()
    lead = _seed(repo, tenant, workspace)
    existing = await repo.create_message(
        NewOutreachMessage(
            tenant_id=tenant,
            workspace_id=workspace,
            channel="social",
            provider="reddit",
            lead_id=lead.id,
            status="draft_ready",
            dedupe_key=f"draft:{lead.id}",
            metadata={"draft_version": 1},
        )
    )
    llm = FakeLLM(_valid_draft())
    notifier = FakeNotifier()

    result = await _draft(
        repo,
        llm,
        notifier,
        tenant,
        workspace,
        lead,
        _settings(tenant, workspace),
        now,
    )

    assert result.id == existing.id
    assert llm.calls == []
    assert len(repo.messages) == 1
    assert repo.outreach_versions == []
    assert repo.approvals == []
    assert repo.outbox == []
    assert await dispatch_outbox(repo, notifier, now=now) == 0
    assert notifier.cards == []


async def test_sent_message_does_not_get_a_fresh_card(repo, now):
    tenant, workspace = uuid4(), uuid4()
    lead = _seed(repo, tenant, workspace)
    existing = await repo.create_message(
        NewOutreachMessage(
            tenant_id=tenant,
            workspace_id=workspace,
            channel="social",
            provider="reddit",
            lead_id=lead.id,
            status="sent",
            dedupe_key=f"draft:{lead.id}",
            metadata={"draft_version": 1},
        )
    )
    await repo.create_version(
        NewOutreachVersion(
            tenant_id=tenant,
            message_id=existing.id,
            version=1,
            body_text=VALID_BODY.replace("{{LINK}}", _expected_url(lead)),
            cta_url=_expected_url(lead),
            model="drafter-v1",
            prompt_version="3",
            risk_flags=[],
        )
    )
    llm = FakeLLM(_valid_draft())
    llm.exc = AssertionError("sent drafts must not call the LLM")
    notifier = FakeNotifier()

    result = await _draft(
        repo,
        llm,
        notifier,
        tenant,
        workspace,
        lead,
        _settings(tenant, workspace),
        now,
    )

    assert result.id == existing.id
    assert len(llm.calls) == 0
    assert len(repo.messages) == 1
    assert len(repo.outreach_versions) == 1
    assert repo.approvals == []
    assert repo.outbox == []
    assert await dispatch_outbox(repo, notifier, now=now) == 0
    assert notifier.cards == []


async def test_retry_after_rejection_returns_without_card(repo, now):
    tenant, workspace = uuid4(), uuid4()
    lead = _seed(repo, tenant, workspace)
    llm = FakeLLM(_valid_draft(body_markdown="I built Example."))
    notifier = FakeNotifier()
    settings = _settings(tenant, workspace)

    first = await _draft(
        repo, llm, notifier, tenant, workspace, lead, settings, now
    )
    assert first.status == "rejected"
    llm.exc = AssertionError("retry must not call the LLM")

    second = await _draft(
        repo, llm, notifier, tenant, workspace, lead, settings, now
    )

    assert second.status == "rejected"
    assert second.id == first.id
    assert len(llm.calls) == 1
    assert len(repo.messages) == 1
    assert repo.outreach_versions == []
    assert repo.approvals == []
    assert repo.outbox == []
    assert await dispatch_outbox(repo, notifier, now=now) == 0
    assert notifier.cards == []


# ---------------------------------------------------------------------------
# Configuration and provider failures
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "field,error",
    [
        ("product_url", "PROVIDER_NOT_CONFIGURED: product_url"),
        ("product_domain", "PROVIDER_NOT_CONFIGURED: product_domain"),
        ("feishu_chat_id", "PROVIDER_NOT_CONFIGURED: feishu_chat_id"),
    ],
)
async def test_empty_settings_raise_provider_not_configured(
    repo, now, field, error
):
    tenant, workspace = uuid4(), uuid4()
    lead = _seed(repo, tenant, workspace)
    llm = FakeLLM(_valid_draft())
    settings = _settings(tenant, workspace, **{field: ""})

    with pytest.raises(ProviderNotConfigured) as excinfo:
        await _draft(
            repo, llm, FakeNotifier(), tenant, workspace, lead, settings, now
        )

    assert str(excinfo.value) == error
    assert llm.calls == []
    assert repo.messages == []
    assert repo.outreach_versions == []
    assert repo.audit == []


async def test_missing_prompt_raises_provider_not_configured(repo, now):
    tenant, workspace = uuid4(), uuid4()
    lead = _add_lead(repo, tenant, workspace)
    llm = FakeLLM(_valid_draft())

    with pytest.raises(ProviderNotConfigured) as excinfo:
        await _draft(
            repo,
            llm,
            FakeNotifier(),
            tenant,
            workspace,
            lead,
            _settings(tenant, workspace),
            now,
        )

    assert str(excinfo.value) == "PROVIDER_NOT_CONFIGURED: social_reply prompt"
    assert llm.calls == []
    assert repo.messages == []


async def test_missing_lead_raises_lookup_error(repo, now):
    tenant, workspace = uuid4(), uuid4()
    repo.prompts[(tenant, "social_reply", 3)] = _prompt(tenant)
    missing = _make_lead(tenant, workspace)

    with pytest.raises(LookupError) as excinfo:
        await _draft(
            repo,
            FakeLLM(_valid_draft()),
            FakeNotifier(),
            tenant,
            workspace,
            missing,
            _settings(tenant, workspace),
            now,
        )

    assert str(excinfo.value) == "LEAD_NOT_FOUND"


async def test_llm_failure_leaves_no_rows_and_lead_unchanged(repo, now):
    tenant, workspace = uuid4(), uuid4()
    lead = _seed(repo, tenant, workspace)
    llm = FakeLLM(
        exc=ProviderUnavailable("PROVIDER_UNAVAILABLE: llm timeout")
    )
    notifier = FakeNotifier()

    with pytest.raises(ProviderUnavailable):
        await _draft(
            repo,
            llm,
            notifier,
            tenant,
            workspace,
            lead,
            _settings(tenant, workspace),
            now,
        )

    assert repo.messages == []
    assert repo.outreach_versions == []
    assert repo.approvals == []
    assert repo.outbox == []
    assert repo.audit == []
    assert await dispatch_outbox(repo, notifier, now=now) == 0
    assert notifier.cards == []
    stored = await repo.get_lead(tenant, lead.id)
    assert stored is not None
    assert stored.status == "qualified"
