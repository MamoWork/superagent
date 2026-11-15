import os

import asyncpg
import pytest

from growth_core.migrate import apply_migrations

pytestmark = pytest.mark.integration


async def _reset_public_schema(url: str) -> None:
    conn = await asyncpg.connect(url)
    try:
        await conn.execute(
            "drop schema if exists public cascade; create schema public;"
        )
    finally:
        await conn.close()


@pytest.mark.skipif(
    not os.getenv("GROWTH_TEST_DATABASE_URL"),
    reason="GROWTH_TEST_DATABASE_URL is not set",
)
async def test_migrations_are_idempotent():
    url = os.environ["GROWTH_TEST_DATABASE_URL"]
    await _reset_public_schema(url)

    first = await apply_migrations(url)
    second = await apply_migrations(url)

    assert first == ["0001_core"]
    assert second == []

    conn = await asyncpg.connect(url)
    try:
        assert await conn.fetchval("select to_regclass('public.tenants')") is not None
        snapshot_default = await conn.fetchval(
            """
            select column_default
            from information_schema.columns
            where table_schema = 'public'
              and table_name = 'config_versions'
              and column_name = 'snapshot'
            """
        )
    finally:
        await conn.close()

    assert snapshot_default == "'{}'::jsonb"


async def test_apply_migrations_rejects_missing_migrations_dir(tmp_path):
    with pytest.raises(FileNotFoundError):
        await apply_migrations(
            "postgresql://unreachable", tmp_path / "does-not-exist"
        )


async def test_apply_migrations_rejects_empty_migrations_dir(tmp_path):
    with pytest.raises(ValueError):
        await apply_migrations("postgresql://unreachable", tmp_path)
