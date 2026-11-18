"""Tests for bounded, enqueue-only social follow-up generation.

A follow-up check never posts anything. It stops at the cap or once the lead is
closed, reschedules until the minimum interval has elapsed, and otherwise
drafts exactly one follow-up under the same link policy as the first reply,
leaving delivery of its Feishu card to the outbox dispatcher.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlsplit
from uuid import UUID, uuid4

import pytest

from growth_core import seed_data
from growth_core.adapters.base import ProviderNotConfigured, ProviderUnavailable
from growth_core.config import GrowthSettings
from growth_core.schemas import (
    NewOutreachVersion,
    NewTask,
    OutreachMessage,
    PromptTemplate,
    SocialLead,
)
from growth_core.services.outbox import dispatch_outbox
from growth_social.schemas import ReplyDraft
from growth_social.services.followup import process_followup_check
from tests.growth.fakes import FakeGrowthRepository, FakeNotifier

CLOCK = datetime(2026, 11, 15, 9, 0, tzinfo=timezone.utc)

PREVIOUS_REPLY = "First reply: I built Example and shared an onboarding checklist."

BODY = (
    "The first reply covered the welcome sequence gap. One extra check that "
    "helps: I built Example, and this checklist covers it: {{LINK}}"
)

URL_PATTERN = re.compile(r"https?://[^\s)\]>]+")


class FakeLLM:
    """Deterministic LLM double that records every call."""

    model = "fake-followup-drafter"

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
        "body_markdown": BODY,
        "link_path": "/guides/onboarding-checklist",
        "risk_flags": ["no_promises"],
    }
    data.update(overrides)
    return ReplyDraft(**data)


def _prompt(tenant_id: UUID, version: int = 3) -> PromptTemplate:
    return PromptTemplate(
        id=uuid4(),
        tenant_id=tenant_id,
        key="social_followup",
        module="social",
        version=version,
        template=seed_data.SOCIAL_FOLLOWUP_SYSTEM,
        user_template=seed_data.SOCIAL_FOLLOWUP_USER,
        output_schema=seed_data.PROMPT_OUTPUT_SCHEMA,
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
        "product_name": "",
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
        "author_public": "alice",
        "source_url": "https://reddit.example/r/SaaS/post/1",
        "subreddit": "SaaS",
        "dedupe_key": str(uuid4()),
        "status": "qualified",
        "score": 91,
        "created_at": now,
        "updated_at": now,
    }
    data.update(overrides)
    return SocialLead(**data)


def _make_original(
    lead: SocialLead,
    *,
    now: datetime = CLOCK,
    status: str = "sent",
    **overrides,
) -> OutreachMessage:
    data = {
        "id": uuid4(),
        "tenant_id": lead.tenant_id,
        "workspace_id": lead.workspace_id,
        "channel": "social",
        "provider": lead.platform,
        "lead_id": lead.id,
        "status": status,
        "dedupe_key": f"draft:{lead.id}",
        "metadata": {"subreddit": lead.subreddit, "has_link": True},
        "sent_at": now if status == "sent" else None,
        "created_at": now,
        "updated_at": now,
    }
    data.update(overrides)
    return OutreachMessage(**data)


def _seed_followup(
    repo: FakeGrowthRepository,
    original: OutreachMessage,
    index: int,
    *,
    status: str = "sent",
    sent_at: datetime | None = None,
) -> OutreachMessage:
    message = OutreachMessage(
        id=uuid4(),
        tenant_id=original.tenant_id,
        workspace_id=original.workspace_id,
        channel="social",
        provider=original.provider,
        lead_id=original.lead_id,
        status=status,
        dedupe_key=f"followup:{original.id}:{index}",
        metadata={
            "followup_of": str(original.id),
            "followup_index": index,
        },
        sent_at=sent_at,
        created_at=CLOCK,
        updated_at=CLOCK,
    )
    repo.messages.append(message)
    return message


async def _seed(
    repo: FakeGrowthRepository,
    tenant_id: UUID,
    workspace_id: UUID,
    *,
    prompt: bool = True,
    previous_reply: str | None = PREVIOUS_REPLY,
    **lead_overrides,
) -> tuple[SocialLead, OutreachMessage]:
    if prompt:
        repo.prompts[(tenant_id, "social_followup", 3)] = _prompt(tenant_id)
    lead = _make_lead(tenant_id, workspace_id, **lead_overrides)
    repo.leads.append(lead)
    original = _make_original(lead)
    repo.messages.append(original)
    if previous_reply is not None:
        await repo.create_version(
            NewOutreachVersion(
                tenant_id=tenant_id,
                message_id=original.id,
                version=1,
                body_text=previous_reply,
                cta_url="https://example.com/first",
                prompt_version="2",
            )
        )
    return lead, original


async def _process(
    repo: FakeGrowthRepository,
    llm: FakeLLM,
    notifier: FakeNotifier,
    tenant_id: UUID,
    workspace_id: UUID,
    original: OutreachMessage | UUID,
    settings: GrowthSettings,
    at: datetime = CLOCK,
) -> OutreachMessage | None:
    original_id = (
        original.id if isinstance(original, OutreachMessage) else original
    )
    return await process_followup_check(
        repo,
        llm,
        notifier,
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        original_message_id=original_id,
        settings=settings,
        now=at,
    )


def _expected_url(lead: SocialLead) -> str:
    return (
        "https://example.com/guides/onboarding-checklist"
        f"?utm_source=reddit&utm_medium=reply&utm_campaign={lead.id}"
    )


def _created_audits(repo: FakeGrowthRepository) -> list[dict]:
    return [
        entry
        for entry in repo.audit
        if entry["action"] == "social.followup_created"
    ]


# ---------------------------------------------------------------------------
# Rescheduling
# ---------------------------------------------------------------------------


async def test_followup_reschedules_until_one_day(repo, now):
    tenant, workspace = uuid4(), uuid4()
    lead, original = await _seed(repo, tenant, workspace)
    llm = FakeLLM(_valid_draft())
    notifier = FakeNotifier()
    settings = _settings(tenant, workspace)

    # Task 19's mark_sent already queued the day-one check.
    await repo.enqueue_task(
        NewTask(
            tenant_id=tenant,
            workspace_id=workspace,
            pipeline="social",
            task_type="social.followup_check",
            payload={"original_message_id": str(original.id)},
            idempotency_key=f"followup:{original.id}:{original.id}",
            run_after=now + timedelta(days=1),
        )
    )

    at = now + timedelta(hours=23)
    result = await _process(
        repo, llm, notifier, tenant, workspace, original, settings, at
    )

    assert result is None
    tasks = repo.tasks_for(f"followup:{original.id}")
    assert len(tasks) == 2
    retry = next(task for task in tasks if "retry" in task.idempotency_key)
    assert retry.task_type == "social.followup_check"
    assert retry.pipeline == "social"
    assert retry.payload == {"original_message_id": str(original.id)}
    assert retry.idempotency_key == (
        f"followup:{original.id}:retry:{int(at.timestamp())}"
    )
    assert retry.run_after == now + timedelta(hours=24)

    assert llm.calls == []
    assert len(repo.messages) == 1
    assert repo.outbox == []
    assert notifier.cards == []


async def test_followup_uses_configured_minimum_interval(repo, now):
    tenant, workspace = uuid4(), uuid4()
    lead, original = await _seed(repo, tenant, workspace)
    settings = _settings(tenant, workspace, followup_min_interval_hours=2)
    at = now + timedelta(hours=1)

    result = await _process(
        repo,
        FakeLLM(_valid_draft()),
        FakeNotifier(),
        tenant,
        workspace,
        original,
        settings,
        at,
    )

    assert result is None
    tasks = repo.tasks_for(f"followup:{original.id}")
    assert len(tasks) == 1
    assert tasks[0].run_after == now + timedelta(hours=2)
    assert tasks[0].idempotency_key == (
        f"followup:{original.id}:retry:{int(at.timestamp())}"
    )


async def test_followup_stop_precedes_reschedule_at_one_hour(repo, now):
    tenant, workspace = uuid4(), uuid4()
    lead, original = await _seed(repo, tenant, workspace)
    lead.status = "replied"
    notifier = FakeNotifier()

    result = await _process(
        repo,
        FakeLLM(_valid_draft()),
        notifier,
        tenant,
        workspace,
        original,
        _settings(tenant, workspace),
        now + timedelta(hours=1),
    )

    # A stopped lead is turned away before the interval is even considered.
    assert result is None
    assert repo.tasks == []
    assert repo.outbox == []
    assert notifier.cards == []


async def test_followup_proceeds_when_last_sent_at_is_none(repo, now):
    tenant, workspace = uuid4(), uuid4()
    lead, original = await _seed(repo, tenant, workspace)
    original.sent_at = None
    llm = FakeLLM(_valid_draft())

    message = await _process(
        repo,
        llm,
        FakeNotifier(),
        tenant,
        workspace,
        original,
        _settings(tenant, workspace),
        now + timedelta(hours=1),
    )

    assert message is not None
    assert message.status == "draft_ready"
    assert len(repo.tasks_for(f"followup:{original.id}")) == 0


# ---------------------------------------------------------------------------
# Creation
# ---------------------------------------------------------------------------


async def test_followup_creates_one_draft_after_one_day(repo, now):
    tenant, workspace = uuid4(), uuid4()
    lead, original = await _seed(repo, tenant, workspace)
    llm = FakeLLM(_valid_draft())
    notifier = FakeNotifier()
    settings = _settings(tenant, workspace)
    at = now + timedelta(hours=24)
    expected_url = _expected_url(lead)

    message = await _process(
        repo, llm, notifier, tenant, workspace, original, settings, at
    )

    # One new message, keyed deterministically -------------------------
    assert message is not None
    assert message.id != original.id
    assert message.status == "draft_ready"
    assert message.channel == "social"
    assert message.provider == "reddit"
    assert message.workspace_id == workspace
    assert message.lead_id == lead.id
    assert message.dedupe_key == f"followup:{original.id}:1"
    assert message.metadata == {
        "followup_of": str(original.id),
        "followup_index": 1,
        "subreddit": "SaaS",
        "has_link": True,
        "draft_version": 1,
    }
    assert len(repo.messages) == 2

    # Version 1 --------------------------------------------------------
    version = await repo.get_latest_version(tenant, message.id)
    assert version is not None
    assert version.version == 1
    assert version.body_text == BODY.replace("{{LINK}}", expected_url)
    assert version.cta_url == expected_url
    assert version.model == "fake-followup-drafter"
    assert version.prompt_version == "3"
    assert version.risk_flags == ["no_promises"]
    assert len(repo.outreach_versions) == 2  # original + follow-up

    # Exactly one official link with UTM and a disclosure --------------
    urls = URL_PATTERN.findall(version.body_text)
    assert len(urls) == 1
    assert "{{LINK}}" not in version.body_text
    parts = urlsplit(urls[0])
    assert parts.scheme == "https"
    assert parts.hostname == "example.com"
    assert parts.path == "/guides/onboarding-checklist"
    assert parse_qs(parts.query) == {
        "utm_source": ["reddit"],
        "utm_medium": ["reply"],
        "utm_campaign": [str(lead.id)],
    }
    prefix = version.body_text[: version.body_text.find(urls[0])].lower()
    assert "i built example" in prefix

    # Approval and enqueue-only card -----------------------------------
    approval_id = f"{message.id}:v1"
    approval = await repo.get_approval_request(tenant, approval_id)
    assert approval is not None
    assert approval.message_id == message.id
    assert approval.provider == "feishu"
    assert approval.payload == {"chat_id": "oc_chat"}
    assert approval.status == "pending"
    assert len(repo.approvals) == 1

    rows = repo.outbox_for(f"feishu:{approval_id}")
    assert len(rows) == 1
    assert rows[0].topic == "feishu.card"
    assert notifier.cards == []

    delivered = await dispatch_outbox(repo, notifier, now=at)
    assert delivered == 1
    assert len(notifier.cards) == 1
    assert notifier.cards[0] == rows[0].payload["card"]

    # Audit and lead ----------------------------------------------------
    created = _created_audits(repo)
    assert len(created) == 1
    assert created[0]["tenant_id"] == tenant
    assert created[0]["workspace_id"] == workspace
    assert created[0]["actor_type"] == "service"
    assert created[0]["entity_type"] == "outreach_message"
    assert created[0]["entity_id"] == message.id
    assert created[0]["after"] == {
        "original_message_id": str(original.id),
        "followup_index": 1,
    }

    stored_lead = await repo.get_lead(tenant, lead.id)
    assert stored_lead is not None
    assert stored_lead.status == "qualified"


async def test_followup_renders_prompt_with_previous_reply_and_index(repo, now):
    tenant, workspace = uuid4(), uuid4()
    lead, original = await _seed(repo, tenant, workspace)
    llm = FakeLLM(_valid_draft())
    settings = _settings(tenant, workspace)

    await _process(
        repo,
        llm,
        FakeNotifier(),
        tenant,
        workspace,
        original,
        settings,
        now + timedelta(hours=24),
    )

    assert len(llm.calls) == 1
    call = llm.calls[0]
    assert call["system"] == seed_data.SOCIAL_FOLLOWUP_SYSTEM
    assert call["schema"] is ReplyDraft
    assert call["model"] == "drafter-v1"
    assert call["user"] == (
        "Original post title: How do you keep onboarding emails personal?\n"
        "Original post body: Our welcome sequence feels generic after 200 "
        "signups.\n"
        f"Previous reply: {PREVIOUS_REPLY}\n"
        "Follow-up number: 1\n"
        "Product: example.com\n"
    )


async def test_followup_uses_product_name_in_prompt(repo, now):
    tenant, workspace = uuid4(), uuid4()
    lead, original = await _seed(repo, tenant, workspace)
    llm = FakeLLM(_valid_draft())

    await _process(
        repo,
        llm,
        FakeNotifier(),
        tenant,
        workspace,
        original,
        _settings(tenant, workspace, product_name="Example App"),
        now + timedelta(hours=24),
    )

    assert "Product: Example App\n" in llm.calls[0]["user"]


async def test_followup_handles_missing_previous_version(repo, now):
    tenant, workspace = uuid4(), uuid4()
    lead, original = await _seed(repo, tenant, workspace, previous_reply=None)
    llm = FakeLLM(_valid_draft())

    message = await _process(
        repo,
        llm,
        FakeNotifier(),
        tenant,
        workspace,
        original,
        _settings(tenant, workspace),
        now + timedelta(hours=24),
    )

    assert message is not None
    assert "Previous reply: \n" in llm.calls[0]["user"]


async def test_followup_index_increments(repo, now):
    tenant, workspace = uuid4(), uuid4()
    lead, original = await _seed(repo, tenant, workspace)
    _seed_followup(repo, original, 1)
    _seed_followup(repo, original, 2)
    llm = FakeLLM(_valid_draft())

    message = await _process(
        repo,
        llm,
        FakeNotifier(),
        tenant,
        workspace,
        original,
        _settings(tenant, workspace),
        now + timedelta(hours=24),
    )

    assert message is not None
    assert message.metadata["followup_index"] == 3
    assert message.dedupe_key == f"followup:{original.id}:3"
    assert "Follow-up number: 3\n" in llm.calls[0]["user"]


# ---------------------------------------------------------------------------
# Caps and closed leads
# ---------------------------------------------------------------------------


async def test_followup_stops_after_three(repo, now):
    tenant, workspace = uuid4(), uuid4()
    lead, original = await _seed(repo, tenant, workspace)
    for index in (1, 2, 3):
        _seed_followup(repo, original, index)
    llm = FakeLLM(_valid_draft())
    notifier = FakeNotifier()

    result = await _process(
        repo,
        llm,
        notifier,
        tenant,
        workspace,
        original,
        _settings(tenant, workspace),
        now + timedelta(hours=24),
    )

    assert result is None
    assert llm.calls == []
    assert len(repo.messages) == 4  # original + three follow-ups
    assert repo.outbox == []
    assert notifier.cards == []
    assert repo.tasks == []


@pytest.mark.parametrize(
    "lead_status", ["replied", "converted", "suppressed", "rejected"]
)
async def test_followup_stops_when_lead_is_closed(repo, now, lead_status):
    tenant, workspace = uuid4(), uuid4()
    lead, original = await _seed(repo, tenant, workspace)
    lead.status = lead_status
    llm = FakeLLM(_valid_draft())
    notifier = FakeNotifier()

    result = await _process(
        repo,
        llm,
        notifier,
        tenant,
        workspace,
        original,
        _settings(tenant, workspace),
        now + timedelta(hours=24),
    )

    assert result is None
    assert llm.calls == []
    assert len(repo.messages) == 1
    assert repo.outbox == []
    assert notifier.cards == []


async def test_followup_stops_when_lead_replied(repo, now):
    tenant, workspace = uuid4(), uuid4()
    lead, original = await _seed(repo, tenant, workspace)
    await repo.update_lead_status(
        tenant, lead.id, expected_status="qualified", status="replied"
    )
    notifier = FakeNotifier()

    result = await _process(
        repo,
        FakeLLM(_valid_draft()),
        notifier,
        tenant,
        workspace,
        original,
        _settings(tenant, workspace),
        now + timedelta(hours=24),
    )

    assert result is None
    assert notifier.cards == []
    assert not _created_audits(repo)


async def test_followup_stops_when_author_is_suppressed(repo, now):
    tenant, workspace = uuid4(), uuid4()
    lead, original = await _seed(repo, tenant, workspace)
    await repo.add_suppression(
        tenant, "platform_user", f"{lead.platform}:{lead.author_public}",
        "negative_reply",
    )
    llm = FakeLLM(_valid_draft())
    notifier = FakeNotifier()

    result = await _process(
        repo,
        llm,
        notifier,
        tenant,
        workspace,
        original,
        _settings(tenant, workspace),
        now + timedelta(hours=24),
    )

    assert result is None
    assert llm.calls == []
    assert len(repo.messages) == 1
    assert repo.outbox == []
    assert notifier.cards == []


async def test_followup_without_public_author_skips_suppression(repo, now):
    tenant, workspace = uuid4(), uuid4()
    lead, original = await _seed(
        repo, tenant, workspace, author_public=None
    )
    await repo.add_suppression(
        tenant, "platform_user", f"{lead.platform}:none", "negative_reply"
    )

    message = await _process(
        repo,
        FakeLLM(_valid_draft()),
        FakeNotifier(),
        tenant,
        workspace,
        original,
        _settings(tenant, workspace),
        now + timedelta(hours=24),
    )

    assert message is not None
    assert message.status == "draft_ready"


@pytest.mark.parametrize("status", ["approved", "draft_ready", "rejected"])
async def test_followup_stops_when_original_was_not_sent(repo, now, status):
    tenant, workspace = uuid4(), uuid4()
    lead, original = await _seed(repo, tenant, workspace)
    original.status = status
    original.sent_at = None
    llm = FakeLLM(_valid_draft())
    notifier = FakeNotifier()

    result = await _process(
        repo,
        llm,
        notifier,
        tenant,
        workspace,
        original,
        _settings(tenant, workspace),
        now + timedelta(hours=24),
    )

    assert result is None
    assert llm.calls == []
    assert len(repo.messages) == 1
    assert repo.outbox == []
    assert notifier.cards == []


async def test_followup_stops_when_original_is_missing(repo, now):
    tenant, workspace = uuid4(), uuid4()
    llm = FakeLLM(_valid_draft())
    notifier = FakeNotifier()

    result = await _process(
        repo,
        llm,
        notifier,
        tenant,
        workspace,
        uuid4(),
        _settings(tenant, workspace),
        now + timedelta(hours=24),
    )

    assert result is None
    assert llm.calls == []
    assert repo.messages == []
    assert repo.outbox == []
    assert notifier.cards == []


async def test_followup_stops_when_lead_is_missing(repo, now):
    tenant, workspace = uuid4(), uuid4()
    lead, original = await _seed(repo, tenant, workspace)
    original.lead_id = uuid4()
    llm = FakeLLM(_valid_draft())

    result = await _process(
        repo,
        llm,
        FakeNotifier(),
        tenant,
        workspace,
        original,
        _settings(tenant, workspace),
        now + timedelta(hours=24),
    )

    assert result is None
    assert llm.calls == []
    assert len(repo.messages) == 1


# ---------------------------------------------------------------------------
# Link and placeholder policy
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "body",
    [
        "No placeholder at all, just a plain follow-up.",
        "Two links {{LINK}} and another {{LINK}}.",
    ],
)
async def test_followup_rejected_when_placeholder_count_is_not_one(
    repo, now, body
):
    tenant, workspace = uuid4(), uuid4()
    lead, original = await _seed(repo, tenant, workspace)
    llm = FakeLLM(_valid_draft(body_markdown=body))
    notifier = FakeNotifier()

    message = await _process(
        repo,
        llm,
        notifier,
        tenant,
        workspace,
        original,
        _settings(tenant, workspace),
        now + timedelta(hours=24),
    )

    assert message is not None
    assert message.status == "rejected"
    assert message.dedupe_key == f"followup:{original.id}:1"
    assert message.metadata == {"policy_violations": ["PLACEHOLDER_COUNT"]}
    assert await repo.get_latest_version(tenant, message.id) is None
    assert repo.approvals == []
    assert repo.outbox == []
    assert notifier.cards == []

    audits = [
        entry
        for entry in repo.audit
        if entry["action"] == "social.followup_rejected"
    ]
    assert len(audits) == 1
    assert audits[0]["after"] == {"policy_violations": ["PLACEHOLDER_COUNT"]}
    assert _created_audits(repo) == []


async def test_followup_suppressed_when_subreddit_disallows_links(repo, now):
    tenant, workspace = uuid4(), uuid4()
    lead, original = await _seed(
        repo,
        tenant,
        workspace,
        subreddit_rules={"self_promotion_allowed": False},
    )
    llm = FakeLLM(_valid_draft())
    notifier = FakeNotifier()

    message = await _process(
        repo,
        llm,
        notifier,
        tenant,
        workspace,
        original,
        _settings(tenant, workspace),
        now + timedelta(hours=24),
    )

    assert message is not None
    assert message.status == "suppressed"
    assert message.metadata == {"policy_violations": ["SUBREDDIT_NO_LINKS"]}
    assert await repo.get_latest_version(tenant, message.id) is None
    assert repo.approvals == []
    assert repo.outbox == []
    assert notifier.cards == []

    audits = [
        entry
        for entry in repo.audit
        if entry["action"] == "social.followup_suppressed"
    ]
    assert len(audits) == 1
    assert audits[0]["after"] == {"policy_violations": ["SUBREDDIT_NO_LINKS"]}


async def test_duplicate_dedupe_returns_existing_without_new_writes(repo, now):
    tenant, workspace = uuid4(), uuid4()
    lead, original = await _seed(repo, tenant, workspace)
    settings = _settings(tenant, workspace)
    at = now + timedelta(hours=24)

    first = await _process(
        repo,
        FakeLLM(_valid_draft()),
        FakeNotifier(),
        tenant,
        workspace,
        original,
        settings,
        at,
    )
    assert first is not None
    messages_before = len(repo.messages)
    versions_before = len(repo.outreach_versions)
    approvals_before = len(repo.approvals)
    outbox_before = len(repo.outbox)

    # Simulate a racing worker that read the count before this row committed.
    async def stale_count(tenant_id, original_message_id):
        return 0

    repo.count_followups = stale_count
    second_llm = FakeLLM(
        _valid_draft(body_markdown="A different {{LINK}} draft.")
    )
    second = await _process(
        repo,
        second_llm,
        FakeNotifier(),
        tenant,
        workspace,
        original,
        settings,
        at,
    )

    assert second is not None
    assert second.id == first.id
    assert second.status == "draft_ready"
    assert second_llm.calls == []
    assert len(repo.messages) == messages_before
    assert len(repo.outreach_versions) == versions_before
    assert len(repo.approvals) == approvals_before
    assert len(repo.outbox) == outbox_before
    assert len(_created_audits(repo)) == 1


async def test_followup_resume_repairs_missing_approval_and_card(repo, now):
    tenant, workspace = uuid4(), uuid4()
    lead, original = await _seed(repo, tenant, workspace)
    settings = _settings(tenant, workspace)
    at = now + timedelta(hours=24)

    created = await _process(
        repo,
        FakeLLM(_valid_draft()),
        FakeNotifier(),
        tenant,
        workspace,
        original,
        settings,
        at,
    )
    assert created is not None
    approval_id = f"{created.id}:v1"
    assert len(repo.approvals) == 1
    assert len(repo.outbox_for(f"feishu:{approval_id}")) == 1

    # Simulate a retry of the same check after both card rows were lost.
    repo.approvals.clear()
    repo.outbox.clear()

    async def stale_count(tenant_id, original_message_id):
        return 0

    repo.count_followups = stale_count
    repaired = await _process(
        repo,
        FakeLLM(_valid_draft()),
        FakeNotifier(),
        tenant,
        workspace,
        original,
        settings,
        at,
    )

    assert repaired is not None
    assert repaired.id == created.id
    assert len(repo.messages) == 2
    assert len(repo.outreach_versions) == 2
    assert len(repo.approvals) == 1
    assert repo.approvals[0].approval_id == approval_id
    assert len(repo.outbox_for(f"feishu:{approval_id}")) == 1
    assert len(repo.outbox) == 1
    assert len(_created_audits(repo)) == 1


async def test_followup_concurrent_create_routes_through_resume(repo, now):
    tenant, workspace = uuid4(), uuid4()
    lead, original = await _seed(repo, tenant, workspace)
    settings = _settings(tenant, workspace)
    at = now + timedelta(hours=24)

    created = await _process(
        repo,
        FakeLLM(_valid_draft()),
        FakeNotifier(),
        tenant,
        workspace,
        original,
        settings,
        at,
    )
    assert created is not None
    approval_id = f"{created.id}:v1"
    repo.approvals.clear()
    repo.outbox.clear()

    # Simulate the ON CONFLICT race: our dedupe lookup missed the row another
    # worker already created and versioned.
    async def stale_count(tenant_id, original_message_id):
        return 0

    async def missed_dedupe(tenant_id, dedupe_key):
        return None

    repo.count_followups = stale_count
    repo.find_message_by_dedupe_key = missed_dedupe
    resumed = await _process(
        repo,
        FakeLLM(_valid_draft()),
        FakeNotifier(),
        tenant,
        workspace,
        original,
        settings,
        at,
    )

    assert resumed is not None
    assert resumed.id == created.id
    assert len(repo.messages) == 2
    assert len(repo.outreach_versions) == 2
    assert len(repo.approvals) == 1
    assert len(repo.outbox_for(f"feishu:{approval_id}")) == 1
    assert len(_created_audits(repo)) == 1


async def test_rejected_followup_is_idempotent_on_retry(repo, now):
    tenant, workspace = uuid4(), uuid4()
    lead, original = await _seed(repo, tenant, workspace)
    settings = _settings(tenant, workspace)
    at = now + timedelta(hours=24)

    first = await _process(
        repo,
        FakeLLM(_valid_draft(body_markdown="No placeholder.")),
        FakeNotifier(),
        tenant,
        workspace,
        original,
        settings,
        at,
    )
    assert first is not None and first.status == "rejected"

    second = await _process(
        repo,
        FakeLLM(_valid_draft()),
        FakeNotifier(),
        tenant,
        workspace,
        original,
        settings,
        at,
    )

    assert second is not None
    assert second.id == first.id
    assert second.status == "rejected"
    assert len(repo.messages) == 2  # original + one rejected follow-up
    assert repo.approvals == []
    assert repo.outbox == []


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


async def test_followup_missing_prompt_raises_provider_not_configured(
    repo, now
):
    tenant, workspace = uuid4(), uuid4()
    lead, original = await _seed(repo, tenant, workspace, prompt=False)
    llm = FakeLLM(_valid_draft())

    with pytest.raises(ProviderNotConfigured) as excinfo:
        await _process(
            repo,
            llm,
            FakeNotifier(),
            tenant,
            workspace,
            original,
            _settings(tenant, workspace),
            now + timedelta(hours=24),
        )

    assert str(excinfo.value) == "PROVIDER_NOT_CONFIGURED: social_followup prompt"
    assert llm.calls == []
    assert len(repo.messages) == 1
    assert repo.outbox == []


async def test_missing_prompt_error_precedes_settings_validation(repo, now):
    tenant, workspace = uuid4(), uuid4()
    lead, original = await _seed(repo, tenant, workspace, prompt=False)
    llm = FakeLLM(_valid_draft())
    settings = _settings(
        tenant,
        workspace,
        product_url="",
        product_domain="",
        feishu_chat_id="",
    )

    with pytest.raises(ProviderNotConfigured) as excinfo:
        await _process(
            repo,
            llm,
            FakeNotifier(),
            tenant,
            workspace,
            original,
            settings,
            now + timedelta(hours=24),
        )

    assert str(excinfo.value) == "PROVIDER_NOT_CONFIGURED: social_followup prompt"
    assert llm.calls == []


async def test_followup_llm_errors_propagate_unchanged(repo, now):
    tenant, workspace = uuid4(), uuid4()
    lead, original = await _seed(repo, tenant, workspace)
    error = ProviderUnavailable("model down")

    with pytest.raises(ProviderUnavailable) as excinfo:
        await _process(
            repo,
            FakeLLM(exc=error),
            FakeNotifier(),
            tenant,
            workspace,
            original,
            _settings(tenant, workspace),
            now + timedelta(hours=24),
        )

    assert excinfo.value is error
    assert len(repo.messages) == 1
    assert repo.outbox == []
