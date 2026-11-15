import os
import pytest

from growth_core.migrate import apply_migrations

pytestmark = pytest.mark.integration


@pytest.mark.skipif(
    not os.getenv("GROWTH_TEST_DATABASE_URL"),
    reason="GROWTH_TEST_DATABASE_URL is not set",
)
async def test_migrations_are_idempotent():
    url = os.environ["GROWTH_TEST_DATABASE_URL"]
    first = await apply_migrations(url)
    second = await apply_migrations(url)
    assert "0001_core" in first
    assert second == []
