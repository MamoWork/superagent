import os
from datetime import datetime, timezone

import pytest


@pytest.fixture
def now() -> datetime:
    return datetime(2026, 11, 15, 9, 0, tzinfo=timezone.utc)


@pytest.fixture
def repo():
    from tests.growth.fakes import FakeGrowthRepository

    return FakeGrowthRepository()


@pytest.fixture
async def pg_repo():
    """Connected Postgres repository with a clean Growth schema.

    Skips when ``GROWTH_TEST_DATABASE_URL`` is unset so the default test run
    stays green. Migrations are idempotent; truncation makes the global
    worker queue (``claim_task`` has no tenant filter) deterministic.
    """
    url = os.environ.get("GROWTH_TEST_DATABASE_URL")
    if not url:
        pytest.skip("GROWTH_TEST_DATABASE_URL is not set")
    from growth_core.migrate import apply_migrations
    from growth_core.repositories.postgres import PostgresGrowthRepository

    await apply_migrations(url)
    repository = await PostgresGrowthRepository.connect(url)
    try:
        await repository.truncate_all_for_tests()
        yield repository
    finally:
        await repository.close()
