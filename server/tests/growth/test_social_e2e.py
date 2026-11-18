"""End-to-end proof of the social pipeline through the real task router.

The flow is post -> lead -> score -> draft -> approve -> sent -> follow-up.
Every stage runs through ``run_once`` with the handlers from
``growth_social.handlers``; Feishu cards only leave through
``dispatch_outbox``. No handler posts, comments, or DMs, and the fake platform
adapter exposes no write path at all.
"""

from __future__ import annotations

import asyncio
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlsplit
from uuid import UUID, uuid4

import pytest

from growth_core import seed_data
from growth_core.adapters.base import ProviderNotConfigured, RawPost
from growth_core.adapters.registry import register_adapter
from growth_core.config import GrowthSettings
from growth_core.schemas import (
    GrowthSource,
    NewOutboxMessage,
    NewTask,
    PromptTemplate,
    ProviderConfig,
    RateLimitRule,
    ScoringRubric,
)
from growth_core.services import worker as worker_module
from growth_core.services.outbox import dispatch_outbox
from growth_core.services.worker import TaskRouter, run_once, run_worker_loop
from growth_social.handlers import build_social_adapters, build_social_router
from growth_social.schemas import (
    IntentDimensionDraft,
    IntentScoreDraft,
    ReplyDraft,
)
from growth_social.services import followup as followup_service
from growth_social.services.approval import FeishuAction, handle_approval
from growth_social.services.sending import mark_sent
from tests.growth.fakes import FakeNotifier

#: Fixed clock after wall time so enqueued tasks default to a claimable time
#: (the fake repository stamps ``run_after`` with the real clock when omitted).
NOW = datetime(2030, 1, 1, 9, 0, tzinfo=timezone.utc)
DAY_LATER = NOW + timedelta(days=1)

REPLY_BODY = (
    "That onboarding slog sounds painful. I built Example, and this checklist "
    "helps: {{LINK}}"
)
URL_PATTERN = re.compile(r"https?://[^\s)\]>]+")
WINDOW_SECONDS = 86400


class _FrozenDatetime(datetime):
    """Freeze the wall clock for the follow-up check at ``DAY_LATER``."""

    @classmethod
    def now(cls, tz=None):
        return DAY_LATER if tz is not None else DAY_LATER.replace(tzinfo=None)


class FakeReddit:
    """Read-only platform adapter: it can fetch posts but never write."""

    name = "reddit"
    capabilities: dict = {}

    def __init__(self, posts: list[RawPost]) -> None:
        self.posts = list(posts)
        self.fetch_calls = 0

    async def fetch(self, source: GrowthSource) -> list[RawPost]:
        self.fetch_calls += 1
        return list(self.posts)

    async def health(self):
        return None

    def validate_config(self) -> None:
        return None


class _FakeSource:
    name = "fake_source"
    capabilities: dict = {"social_source": True}

    async def fetch(self, source: GrowthSource) -> list[RawPost]:
        return []

    async def health(self):
        return None

    def validate_config(self) -> None:
        return None


class _FakeNotifierAdapter:
    async def send_card(self, chat_id: str, card: dict) -> str:
        return "fake-card"

    async def health(self):
        return None


class _FakeLLMAdapter:
    async def complete_json(self, *, system, user, schema, model=None):
        raise AssertionError("composition-root tests must not call the LLM")


def _register_fake_factories() -> None:
    """Register offline factories under test-only provider names."""
    register_adapter(
        "social_source", "fake_source"
    )(lambda config, secrets: _FakeSource())
    register_adapter(
        "notifier", "fake_notifier"
    )(lambda config, secrets: _FakeNotifierAdapter())
    register_adapter(
        "llm", "fake_llm"
    )(lambda config, secrets: _FakeLLMAdapter())


def _provider(
    tenant_id: UUID, capability: str, provider: str
) -> ProviderConfig:
    return ProviderConfig(
        tenant_id=tenant_id,
        capability=capability,
        provider=provider,
        priority=10,
        enabled=True,
        config={},
        secret_ref=None,
    )


class PipelineLLM:
    """One deterministic LLM double covering both scoring and drafting."""

    model = "fake-pipeline-model"

    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.intent = IntentScoreDraft(
            dimensions=[
                IntentDimensionDraft(
                    dimension_id=dimension["id"], score=10, rationale="strong"
                )
                for dimension in seed_data.SCORING_RUBRIC_DIMENSIONS
            ],
            summary="Strong, specific founder fit.",
        )
        self.reply = ReplyDraft(
            body_markdown=REPLY_BODY,
            link_path="/guides/churn",
            risk_flags=["no_promises"],
        )

    async def complete_json(self, *, system, user, schema, model=None):
        self.calls.append(
            {"system": system, "user": user, "schema": schema, "model": model}
        )
        if schema is IntentScoreDraft:
            return self.intent
        if schema is ReplyDraft:
            return self.reply
        raise AssertionError(f"unexpected schema: {schema}")


def _settings(tenant_id: UUID, workspace_id: UUID) -> GrowthSettings:
    return GrowthSettings(
        database_url="postgresql://unused",
        service_token="service-token",
        tenant_id=str(tenant_id),
        workspace_id=str(workspace_id),
        feishu_chat_id="oc_chat",
        product_name="Example",
        product_url="https://example.com",
        product_domain="example.com",
        llm_scoring_model="scorer-v1",
        llm_drafting_model="drafter-v1",
        global_daily_limit=50,
        reddit_daily_limit=5,
        subreddit_link_daily_limit=2,
        followup_max_total=3,
        followup_min_interval_hours=24,
    )


def _prompt(tenant_id: UUID, key: str) -> PromptTemplate:
    system, user = next(
        (system, user)
        for prompt_key, system, user in seed_data.PROMPT_TEMPLATES
        if prompt_key == key
    )
    return PromptTemplate(
        id=uuid4(),
        tenant_id=tenant_id,
        key=key,
        module="social",
        version=seed_data.PROMPT_VERSION,
        template=system,
        user_template=user,
        output_schema=seed_data.PROMPT_OUTPUT_SCHEMA,
        enabled=True,
    )


def _rubric(tenant_id: UUID) -> ScoringRubric:
    return ScoringRubric(
        id=uuid4(),
        tenant_id=tenant_id,
        key=seed_data.SCORING_RUBRIC_KEY,
        version=seed_data.SCORING_RUBRIC_VERSION,
        dimensions=[dict(item) for item in seed_data.SCORING_RUBRIC_DIMENSIONS],
        penalties=[dict(item) for item in seed_data.SCORING_RUBRIC_PENALTIES],
        thresholds=dict(seed_data.SCORING_RUBRIC_THRESHOLDS),
        enabled=True,
    )


def _rate_rule(
    tenant_id: UUID, scope: str, scope_key: str, max_count: int
) -> RateLimitRule:
    return RateLimitRule(
        tenant_id=tenant_id,
        channel="social",
        scope=scope,
        scope_key=scope_key,
        window_seconds=WINDOW_SECONDS,
        max_count=max_count,
        enabled=True,
    )


def _post() -> RawPost:
    return RawPost(
        platform="reddit",
        platform_post_id="e2e-1",
        title="How do you keep onboarding emails personal?",
        body="Our welcome sequence feels generic after 200 signups.",
        author_public="u/alice",
        source_url="https://www.reddit.com/r/SaaS/comments/e2e-1/x/",
        published_at=NOW - timedelta(days=1),
        metrics={"score": 42},
        subreddit="SaaS",
        raw={"id": "e2e-1"},
    )


async def _seed(repo, tenant_id: UUID, workspace_id: UUID) -> GrowthSource:
    for key in ("social_intent", "social_reply", "social_followup"):
        repo.prompts[(tenant_id, key, seed_data.PROMPT_VERSION)] = _prompt(
            tenant_id, key
        )
    repo.rubrics[
        (tenant_id, seed_data.SCORING_RUBRIC_KEY, seed_data.SCORING_RUBRIC_VERSION)
    ] = _rubric(tenant_id)
    for scope, scope_key, max_count in (
        ("global", "*", 50),
        ("platform", "reddit", 5),
        ("subreddit", "*", 2),
    ):
        repo.rate_rules[(tenant_id, "social", scope, scope_key)] = _rate_rule(
            tenant_id, scope, scope_key, max_count
        )

    source = GrowthSource(
        id=uuid4(),
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        source_type="reddit",
        platform="reddit",
        dedupe_key="reddit:r/SaaS",
        config={
            "subreddit": "SaaS",
            "subreddit_rules": {"self_promotion_allowed": True},
        },
        cadence_minutes=30,
        enabled=True,
    )
    await repo.add_source(source)
    return source


async def _seed_ingest_task(
    repo, tenant_id: UUID, workspace_id: UUID
) -> None:
    await repo.enqueue_task(
        NewTask(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            pipeline="social",
            task_type="social.ingest",
            payload={},
            idempotency_key="ingest:e2e-1",
            run_after=NOW,
        )
    )


def _assert_one_official_link(body: str, lead_id: UUID) -> None:
    urls = URL_PATTERN.findall(body)
    assert len(urls) == 1
    assert "{{LINK}}" not in body
    parts = urlsplit(urls[0])
    assert parts.scheme == "https"
    assert parts.hostname == "example.com"
    assert parts.path == "/guides/churn"
    assert parse_qs(parts.query) == {
        "utm_source": ["reddit"],
        "utm_medium": ["reply"],
        "utm_campaign": [str(lead_id)],
    }
    assert "I built Example" in body


async def test_social_flow_from_post_to_followup(repo, monkeypatch):
    tenant_id, workspace_id = uuid4(), uuid4()
    settings = _settings(tenant_id, workspace_id)
    source = await _seed(repo, tenant_id, workspace_id)
    reddit = FakeReddit([_post()])
    llm = PipelineLLM()
    notifier = FakeNotifier()
    router = build_social_router(
        repo=repo,
        adapters={"reddit": reddit},
        notifier=notifier,
        llm=llm,
        settings=settings,
    )
    await _seed_ingest_task(repo, tenant_id, workspace_id)

    # 1. Ingest: one post becomes one lead plus one score task -----------
    assert await run_once(repo, router, worker_id="w1", now=NOW) is True
    assert reddit.fetch_calls == 1
    assert len(repo.leads) == 1
    lead = repo.leads[0]
    assert lead.platform == "reddit"
    assert lead.status == "discovered"
    assert lead.source_id == source.id
    assert len(repo.tasks_for(f"score:{lead.id}")) == 1
    assert notifier.calls == []

    # 2. Score: a qualified lead queues exactly one draft -----------------
    assert await run_once(repo, router, worker_id="w1", now=NOW) is True
    scored = await repo.get_lead(tenant_id, lead.id)
    assert scored is not None
    assert scored.status == "qualified"
    assert scored.score == 100
    assert len(repo.tasks_for(f"draft:{lead.id}")) == 1
    assert notifier.calls == []

    # 3. Draft: enqueue-only, no card delivered by the handler ------------
    assert await run_once(repo, router, worker_id="w1", now=NOW) is True
    message = await repo.find_message_by_dedupe_key(
        tenant_id, f"draft:{lead.id}"
    )
    assert message is not None
    assert message.status == "draft_ready"
    approval_id = f"{message.id}:v1"
    assert len(repo.outbox_for(f"feishu:{approval_id}")) == 1
    assert notifier.calls == []
    first_version = await repo.get_latest_version(tenant_id, message.id)
    assert first_version is not None
    _assert_one_official_link(first_version.body_text, lead.id)
    assert await run_once(repo, router, worker_id="w1", now=NOW) is False

    # 4. Only dispatch_outbox delivers the first approval card ------------
    assert await dispatch_outbox(repo, notifier, now=NOW) == 1
    assert len(notifier.calls) == 1
    card = notifier.cards[0]
    assert card["header"]["title"]["content"] == "Social reply approval"
    assert "https://example.com/" in card["elements"][-1]["text"]["content"]
    assert first_version.body_text in [
        element.get("text", {}).get("content")
        for element in card["elements"]
    ]

    # 5. Feishu approval only moves database state ------------------------
    result = await handle_approval(
        repo,
        tenant_id=tenant_id,
        action=FeishuAction(
            approval_id=approval_id, action="approve", operator="op-1"
        ),
        now=NOW,
    )
    assert result.status == "approved"
    message = await repo.get_message(tenant_id, message.id)
    assert message is not None and message.status == "approved"
    assert notifier.calls and len(notifier.calls) == 1

    # 6. A human posts it; mark_sent records the send and queues the check.
    message = await mark_sent(
        repo,
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        message_id=message.id,
        sent_at=NOW,
        channel="manual",
        now=NOW,
    )
    assert message.status == "sent"
    assert len(repo.deliveries) == 1
    assert repo.deliveries[0]["event_type"] == "sent"
    followup_tasks = repo.tasks_for(f"followup:{message.id}")
    assert len(followup_tasks) == 1
    assert followup_tasks[0].run_after == DAY_LATER
    assert len(notifier.calls) == 1  # sending a card is never a side effect

    # 7. At +24h the follow-up check drafts, then dispatch delivers card 2.
    # The handler passes no ``now`` (worker signature), so freeze the service's
    # wall clock at the same +24h instant the task's ``run_after`` names.
    monkeypatch.setattr(
        followup_service, "datetime", _FrozenDatetime
    )
    assert (
        await run_once(repo, router, worker_id="w1", now=DAY_LATER) is True
    )
    followup = await repo.find_message_by_dedupe_key(
        tenant_id, f"followup:{message.id}:1"
    )
    assert followup is not None
    assert followup.status == "draft_ready"
    assert followup.metadata["followup_of"] == str(message.id)
    assert followup.metadata["followup_index"] == 1
    assert len(notifier.calls) == 1
    assert await run_once(repo, router, worker_id="w1", now=DAY_LATER) is False

    assert await dispatch_outbox(repo, notifier, now=DAY_LATER) == 1
    assert len(notifier.calls) == 2
    second_card = notifier.cards[1]
    assert second_card["header"]["title"]["content"] == "Social reply approval"
    assert "https://example.com/" in second_card["elements"][-1]["text"]["content"]

    version = await repo.get_latest_version(tenant_id, followup.id)
    assert version is not None
    _assert_one_official_link(version.body_text, lead.id)

    # Drafts never call the notifier directly: each card maps one-to-one to an
    # outbox delivery, and both were emitted only by dispatch_outbox.
    assert len(notifier.calls) == len(
        [row for row in repo.outbox if row.status == "sent"]
    )


# ---------------------------------------------------------------------------
# Composition root
# ---------------------------------------------------------------------------


async def test_build_social_adapters_resolves_all_three_capabilities(repo):
    _register_fake_factories()
    tenant_id, workspace_id = uuid4(), uuid4()
    settings = _settings(tenant_id, workspace_id)

    for capability, provider in (
        ("social_source", "fake_source"),
        ("notifier", "fake_notifier"),
        ("llm", "fake_llm"),
    ):
        repo.provider_configs[(tenant_id, capability, provider)] = _provider(
            tenant_id, capability, provider
        )
    await repo.add_source(
        GrowthSource(
            id=uuid4(),
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            source_type="fake_source",
            platform="reddit",
            dedupe_key="fake:source",
            config={},
            cadence_minutes=30,
            enabled=True,
        )
    )

    registry, adapters = await build_social_adapters(repo, settings)

    assert list(adapters) == ["fake_source"]
    assert isinstance(adapters["fake_source"], _FakeSource)
    assert isinstance(registry.notifier(), _FakeNotifierAdapter)
    assert isinstance(registry.llm(), _FakeLLMAdapter)


async def test_build_social_adapters_fails_fast_for_unconfigured_source(repo):
    _register_fake_factories()
    tenant_id, workspace_id = uuid4(), uuid4()
    settings = _settings(tenant_id, workspace_id)

    for capability, provider in (
        ("notifier", "fake_notifier"),
        ("llm", "fake_llm"),
    ):
        repo.provider_configs[(tenant_id, capability, provider)] = _provider(
            tenant_id, capability, provider
        )
    await repo.add_source(
        GrowthSource(
            id=uuid4(),
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            source_type="unconfigured_source",
            platform="reddit",
            dedupe_key="unconfigured:source",
            config={},
            cadence_minutes=30,
            enabled=True,
        )
    )

    with pytest.raises(ProviderNotConfigured) as excinfo:
        await build_social_adapters(repo, settings)

    assert "social_source/unconfigured_source" in str(excinfo.value)


async def test_run_worker_loop_dispatches_when_working_and_sleeps_when_idle(
    repo, monkeypatch
):
    tenant_id, workspace_id = uuid4(), uuid4()
    notifier = FakeNotifier()
    events: list[str] = []
    stop = asyncio.Event()

    async def fake_sleep(seconds: float) -> None:
        events.append("sleep")
        stop.set()

    monkeypatch.setattr(worker_module.asyncio, "sleep", fake_sleep)

    # Record only successful claims and deliveries so the event log names the
    # work that actually happened, not the empty poll noise around it.
    original_claim = repo.claim_task

    async def recording_claim(worker_id, now=None):
        task = await original_claim(worker_id, now=now)
        if task is not None:
            events.append("claim")
        return task

    monkeypatch.setattr(repo, "claim_task", recording_claim)

    original_dispatch = worker_module.dispatch_outbox

    async def recording_dispatch(target_repo, target_notifier, **kwargs):
        sent = await original_dispatch(target_repo, target_notifier, **kwargs)
        if sent:
            events.append("dispatch")
        return sent

    monkeypatch.setattr(worker_module, "dispatch_outbox", recording_dispatch)

    async def handler(task) -> None:
        index = task.payload["index"]
        await repo.enqueue_outbox(
            NewOutboxMessage(
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                topic="feishu.card",
                payload={
                    "chat_id": "oc_chat",
                    "card": {"probe": index},
                    "approval_id": f"loop-approval-{index}",
                },
                idempotency_key=f"outbox:loop:{index}",
            )
        )

    router = TaskRouter()
    router.register("demo", handler)
    for index in (1, 2):
        await repo.enqueue_task(
            NewTask(
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                pipeline="social",
                task_type="demo",
                payload={"index": index},
                idempotency_key=f"demo:loop:{index}",
            )
        )

    await run_worker_loop(
        repo=repo,
        router=router,
        notifier=notifier,
        worker_id="w1",
        poll_seconds=0.5,
        stop=stop,
    )

    # Event order is load-bearing: each claim is followed by the delivery of
    # the card that same iteration queued, and sleep happens only on the
    # following idle iteration. A top-of-loop sleep, a sleep after a working
    # iteration, or an idle-only dispatch all break this exact sequence.
    assert events == ["claim", "dispatch", "claim", "dispatch", "sleep"]

    # End state: both tasks ran, both cards were delivered, in claim order.
    assert notifier.cards == [{"probe": 1}, {"probe": 2}]
    assert repo.outbox_for("outbox:loop:1")[0].status == "sent"
    assert repo.outbox_for("outbox:loop:2")[0].status == "sent"
    assert [task.status for task in repo.tasks] == ["succeeded", "succeeded"]
