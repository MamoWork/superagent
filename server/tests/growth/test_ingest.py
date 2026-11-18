"""Tests for the social ingestion service."""

from __future__ import annotations

import hashlib
from datetime import timedelta
from uuid import UUID, uuid4

from growth_core.adapters.base import (
    ProviderAuthError,
    ProviderUnavailable,
    RawPost,
)
from growth_core.schemas import GrowthSource
from growth_social.services.ingest import IngestResult, SourceError, ingest_social
from tests.growth.fakes import FakeGrowthRepository


class FakeReddit:
    name = "reddit"
    capabilities: dict = {}

    def __init__(self, posts: list[RawPost]) -> None:
        self.posts = list(posts)

    async def fetch(self, source: GrowthSource) -> list[RawPost]:
        return list(self.posts)

    async def health(self):
        return None

    def validate_config(self) -> None:
        return None


class RaisingAdapter:
    """Adapter whose fetch always raises the supplied exception."""

    name = "raising"
    capabilities: dict = {}

    def __init__(self, exc: Exception) -> None:
        self.exc = exc

    async def fetch(self, source: GrowthSource) -> list[RawPost]:
        raise self.exc

    async def health(self):
        return None

    def validate_config(self) -> None:
        return None


def _source(
    *,
    tenant_id: UUID,
    workspace_id: UUID,
    source_type: str = "reddit",
    platform: str = "reddit",
    config: dict | None = None,
    dedupe_key: str | None = None,
    enabled: bool = True,
) -> GrowthSource:
    return GrowthSource(
        id=uuid4(),
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        source_type=source_type,
        platform=platform,
        dedupe_key=dedupe_key or f"{source_type}:{uuid4()}",
        config=config or {},
        cadence_minutes=30,
        enabled=enabled,
    )


def _post(post_id: str = "a1", **overrides) -> RawPost:
    data = {
        "platform": "reddit",
        "platform_post_id": post_id,
        "title": "Churn pain",
        "body": "We track churn manually",
        "author_public": "u/x",
        "source_url": f"https://www.reddit.com/r/saas/comments/{post_id}/x/",
        "published_at": None,
        "metrics": {"score": 3},
        "subreddit": "saas",
        "raw": {"id": post_id},
    }
    data.update(overrides)
    return RawPost(**data)


def _source_row(repo: FakeGrowthRepository, source_id: UUID) -> GrowthSource:
    return next(row for row in repo.sources if row.id == source_id)


async def test_ingest_creates_one_lead_and_one_score_task(repo, now):
    tenant_id, workspace_id = uuid4(), uuid4()
    source = _source(
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        config={"subreddit": "saas"},
        dedupe_key="reddit:r/saas",
    )
    await repo.add_source(source)
    post = _post(published_at=now)
    result = await ingest_social(
        repo,
        {"reddit": FakeReddit([post, post])},
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        now=now,
    )
    assert result.created == 1
    assert result.duplicates == 1
    assert result.errors == []
    assert len(repo.leads) == 1
    assert len(repo.tasks_for(f"score:{repo.leads[0].id}")) == 1


async def test_ingest_continues_after_one_source_error(repo, now):
    tenant_id, workspace_id = uuid4(), uuid4()
    failing = _source(
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        source_type="hackernews",
        platform="hackernews",
    )
    healthy = _source(
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        source_type="reddit",
        platform="reddit",
    )
    await repo.add_source(failing)
    await repo.add_source(healthy)

    result = await ingest_social(
        repo,
        {
            "hackernews": RaisingAdapter(ProviderUnavailable("feed down")),
            "reddit": FakeReddit([_post()]),
        },
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        now=now,
    )

    assert result.created == 1
    assert result.duplicates == 0
    assert result.errors == [
        SourceError(failing.id, "ProviderUnavailable", "feed down")
    ]
    assert [lead.platform for lead in repo.leads] == ["reddit"]
    assert len(repo.tasks_for("score:")) == 1


async def test_missing_adapter_records_error_and_other_source_ingests(repo, now):
    tenant_id, workspace_id = uuid4(), uuid4()
    unconfigured = _source(
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        source_type="mastodon",
        platform="mastodon",
    )
    healthy = _source(
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        source_type="reddit",
        platform="reddit",
    )
    await repo.add_source(unconfigured)
    await repo.add_source(healthy)

    result = await ingest_social(
        repo,
        {"reddit": FakeReddit([_post()])},
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        now=now,
    )

    assert result.created == 1
    assert result.errors == [
        SourceError(
            unconfigured.id,
            "ADAPTER_NOT_CONFIGURED",
            "no adapter for source_type mastodon",
        )
    ]
    row = _source_row(repo, unconfigured.id)
    assert row.last_run_at == now
    assert row.last_error == "ADAPTER_NOT_CONFIGURED: no adapter for source_type mastodon"
    successful_row = _source_row(repo, healthy.id)
    assert successful_row.last_run_at == now
    assert successful_row.last_error is None


async def test_adapter_error_maps_exception_type_and_message(repo, now):
    tenant_id, workspace_id = uuid4(), uuid4()
    source = _source(tenant_id=tenant_id, workspace_id=workspace_id)
    await repo.add_source(source)

    result = await ingest_social(
        repo,
        {"reddit": RaisingAdapter(ProviderAuthError("token rejected"))},
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        now=now,
    )

    assert result.created == 0
    assert result.duplicates == 0
    assert result.errors == [
        SourceError(source.id, "ProviderAuthError", "token rejected")
    ]
    row = _source_row(repo, source.id)
    assert row.last_run_at == now
    assert row.last_error == "ProviderAuthError: token rejected"


async def test_unexpected_exception_maps_to_unexpected_error(repo, now):
    tenant_id, workspace_id = uuid4(), uuid4()
    source = _source(tenant_id=tenant_id, workspace_id=workspace_id)
    await repo.add_source(source)

    result = await ingest_social(
        repo,
        {"reddit": RaisingAdapter(ValueError("boom"))},
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        now=now,
    )

    assert result.created == 0
    assert result.errors == [
        SourceError(source.id, "UNEXPECTED_ERROR", "ValueError: boom")
    ]
    row = _source_row(repo, source.id)
    assert row.last_run_at == now
    assert row.last_error == "UNEXPECTED_ERROR: ValueError: boom"


async def test_update_source_run_marks_success(repo, now):
    tenant_id, workspace_id = uuid4(), uuid4()
    source = _source(tenant_id=tenant_id, workspace_id=workspace_id)
    await repo.add_source(source)
    # Seed a stale error to prove success clears it.
    source.last_error = "old failure"
    source.last_run_at = now - timedelta(days=1)
    repo.sources[0] = source

    await ingest_social(
        repo,
        {"reddit": FakeReddit([_post()])},
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        now=now,
    )

    row = _source_row(repo, source.id)
    assert row.last_run_at == now
    assert row.last_error is None


async def test_dedupe_key_is_exact_sha256_hex(repo, now):
    tenant_id, workspace_id = uuid4(), uuid4()
    await repo.add_source(_source(tenant_id=tenant_id, workspace_id=workspace_id))

    await ingest_social(
        repo,
        {"reddit": FakeReddit([_post("a1")])},
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        now=now,
    )

    expected = hashlib.sha256(b"reddit:a1").hexdigest()
    assert repo.leads[0].dedupe_key == expected
    assert len(expected) == 64


async def test_subreddit_rules_pass_through(repo, now):
    tenant_id, workspace_id = uuid4(), uuid4()
    rules = {"allow_solicitation": False, "flair_required": True}
    source = _source(
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        config={"subreddit": "saas", "subreddit_rules": rules},
    )
    await repo.add_source(source)

    await ingest_social(
        repo,
        {"reddit": FakeReddit([_post()])},
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        now=now,
    )

    lead = repo.leads[0]
    assert lead.subreddit_rules == rules
    assert lead.subreddit == "saas"
    assert lead.source_id == source.id
    assert lead.author_public == "u/x"
    assert lead.metrics == {"score": 3}
    assert lead.raw == {"id": "a1"}


async def test_subreddit_rules_non_dict_falls_back_to_empty(repo, now):
    tenant_id, workspace_id = uuid4(), uuid4()
    source = _source(
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        config={"subreddit_rules": ["not", "a", "dict"]},
    )
    await repo.add_source(source)

    await ingest_social(
        repo,
        {"reddit": FakeReddit([_post()])},
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        now=now,
    )

    assert repo.leads[0].subreddit_rules == {}


async def test_duplicates_do_not_enqueue_extra_score_tasks(repo, now):
    tenant_id, workspace_id = uuid4(), uuid4()
    await repo.add_source(_source(tenant_id=tenant_id, workspace_id=workspace_id))
    post = _post()

    result = await ingest_social(
        repo,
        {"reddit": FakeReddit([post, post, post])},
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        now=now,
    )

    assert result.created == 1
    assert result.duplicates == 2
    assert len(repo.leads) == 1
    assert len(repo.tasks) == 1


async def test_score_task_carries_tenant_workspace_and_payload(repo, now):
    tenant_id, workspace_id = uuid4(), uuid4()
    await repo.add_source(
        _source(
            tenant_id=tenant_id,
            workspace_id=uuid4(),  # deliberately different from the run's workspace
        )
    )

    await ingest_social(
        repo,
        {"reddit": FakeReddit([_post()])},
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        now=now,
    )

    lead = repo.leads[0]
    assert lead.tenant_id == tenant_id
    assert lead.workspace_id == workspace_id
    assert len(repo.tasks) == 1
    task = repo.tasks[0]
    assert task.tenant_id == tenant_id
    assert task.workspace_id == workspace_id
    assert task.pipeline == "social"
    assert task.task_type == "social.score"
    assert task.payload == {"lead_id": str(lead.id)}
    assert task.idempotency_key == f"score:{lead.id}"
    assert task.status == "queued"


async def test_empty_source_list_returns_zeroed_result(repo, now):
    result = await ingest_social(
        repo,
        {},
        tenant_id=uuid4(),
        workspace_id=uuid4(),
        now=now,
    )

    assert result == IngestResult(0, 0)
    assert result.errors == []
    assert IngestResult(0, 0).errors == []


async def test_every_source_uses_the_provided_now(repo, now):
    tenant_id, workspace_id = uuid4(), uuid4()
    older = now - timedelta(hours=3)
    reddit = _source(
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        source_type="reddit",
        platform="reddit",
    )
    hackernews = _source(
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        source_type="hackernews",
        platform="hackernews",
    )
    await repo.add_source(reddit)
    await repo.add_source(hackernews)

    await ingest_social(
        repo,
        {
            "reddit": FakeReddit([_post("a1", published_at=older)]),
            "hackernews": FakeReddit(
                [
                    _post(
                        "h1",
                        platform="hackernews",
                        source_url="https://news.ycombinator.com/item?id=h1",
                        subreddit=None,
                        published_at=older,
                    )
                ]
            ),
        },
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        now=now,
    )

    assert _source_row(repo, reddit.id).last_run_at == now
    assert _source_row(repo, hackernews.id).last_run_at == now
    # Post timestamps are preserved, not overwritten by the run clock.
    assert {lead.published_at for lead in repo.leads} == {older}


class FailingOnceRepository(FakeGrowthRepository):
    """Fails the first upsert of post ``a1`` with a non-adapter exception."""

    def __init__(self) -> None:
        super().__init__()
        self.failed = False

    async def upsert_lead(self, lead):
        if lead.platform_post_id == "a1" and not self.failed:
            self.failed = True
            raise RuntimeError("database unavailable")
        return await super().upsert_lead(lead)


async def test_upsert_failure_skips_remaining_posts_of_that_source(now):
    repo = FailingOnceRepository()
    tenant_id, workspace_id = uuid4(), uuid4()
    failing = _source(
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        source_type="reddit",
        platform="reddit",
    )
    healthy = _source(
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        source_type="hackernews",
        platform="hackernews",
    )
    await repo.add_source(failing)
    await repo.add_source(healthy)

    result = await ingest_social(
        repo,
        {
            "reddit": FakeReddit([_post("a1"), _post("a2")]),
            "hackernews": FakeReddit(
                [
                    _post(
                        "h1",
                        platform="hackernews",
                        source_url="https://news.ycombinator.com/item?id=h1",
                        subreddit=None,
                    )
                ]
            ),
        },
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        now=now,
    )

    assert result.created == 1
    assert result.errors == [
        SourceError(failing.id, "UNEXPECTED_ERROR", "RuntimeError: database unavailable")
    ]
    # The second reddit post was skipped; only the hackernews lead exists.
    assert [lead.platform for lead in repo.leads] == ["hackernews"]
    row = _source_row(repo, failing.id)
    assert row.last_run_at == now
    assert row.last_error == "UNEXPECTED_ERROR: RuntimeError: database unavailable"
    assert _source_row(repo, healthy.id).last_error is None


class FailingUpdateRepository(FakeGrowthRepository):
    """Delegates everything, but ``update_source_run`` raises for selected sources."""

    def __init__(self, fail_source_ids: set[UUID] | None = None) -> None:
        super().__init__()
        self.fail_source_ids = fail_source_ids
        self.update_calls: list[UUID] = []

    async def update_source_run(
        self,
        tenant_id,
        source_id,
        last_run_at,
        last_error=None,
    ) -> None:
        self.update_calls.append(source_id)
        if self.fail_source_ids is None or source_id in self.fail_source_ids:
            raise RuntimeError("store unavailable")
        await super().update_source_run(
            tenant_id, source_id, last_run_at, last_error=last_error
        )


async def test_update_source_run_failure_on_success_does_not_abort_run(now):
    repo = FailingUpdateRepository()
    tenant_id, workspace_id = uuid4(), uuid4()
    failing = _source(
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        source_type="hackernews",
        platform="hackernews",
    )
    healthy = _source(
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        source_type="reddit",
        platform="reddit",
    )
    await repo.add_source(failing)
    await repo.add_source(healthy)
    repo.fail_source_ids = {failing.id}

    result = await ingest_social(
        repo,
        {
            "hackernews": FakeReddit(
                [
                    _post(
                        "h1",
                        platform="hackernews",
                        source_url="https://news.ycombinator.com/item?id=h1",
                        subreddit=None,
                    )
                ]
            ),
            "reddit": FakeReddit([_post("a1")]),
        },
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        now=now,
    )

    assert result.created == 2
    assert result.errors == [
        SourceError(
            failing.id, "UNEXPECTED_ERROR", "RuntimeError: store unavailable"
        )
    ]
    assert [lead.platform for lead in repo.leads] == ["hackernews", "reddit"]
    assert healthy.id in repo.update_calls


async def test_update_source_run_failure_after_adapter_error_keeps_single_error(now):
    repo = FailingUpdateRepository()
    tenant_id, workspace_id = uuid4(), uuid4()
    failing = _source(
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        source_type="hackernews",
        platform="hackernews",
    )
    healthy = _source(
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        source_type="reddit",
        platform="reddit",
    )
    await repo.add_source(failing)
    await repo.add_source(healthy)
    repo.fail_source_ids = {failing.id}

    result = await ingest_social(
        repo,
        {
            "hackernews": RaisingAdapter(ProviderUnavailable("feed down")),
            "reddit": FakeReddit([_post()]),
        },
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        now=now,
    )

    assert result.created == 1
    assert result.errors == [
        SourceError(failing.id, "ProviderUnavailable", "feed down")
    ]
    assert [lead.platform for lead in repo.leads] == ["reddit"]


async def test_update_source_run_failure_on_missing_adapter_keeps_single_error(now):
    repo = FailingUpdateRepository()
    tenant_id, workspace_id = uuid4(), uuid4()
    unconfigured = _source(
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        source_type="hackernews",
        platform="hackernews",
    )
    healthy = _source(
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        source_type="reddit",
        platform="reddit",
    )
    await repo.add_source(unconfigured)
    await repo.add_source(healthy)
    repo.fail_source_ids = {unconfigured.id}

    result = await ingest_social(
        repo,
        {"reddit": FakeReddit([_post()])},
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        now=now,
    )

    assert result.created == 1
    assert result.errors == [
        SourceError(
            unconfigured.id,
            "ADAPTER_NOT_CONFIGURED",
            "no adapter for source_type hackernews",
        )
    ]
    assert [lead.platform for lead in repo.leads] == ["reddit"]
