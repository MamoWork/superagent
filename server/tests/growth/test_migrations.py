import os
import re
import uuid

import asyncpg
import pytest

from growth_core.migrate import DEFAULT_MIGRATIONS_DIR, apply_migrations

pytestmark = pytest.mark.integration

_RLS_ARRAY_RE = re.compile(r"array\[(.*?)\]", re.S)


def _rls_policy_tables() -> list[str]:
    """Return the table names listed in the 0003_rls.sql policy array."""
    sql = (DEFAULT_MIGRATIONS_DIR / "0003_rls.sql").read_text(encoding="utf-8")
    match = _RLS_ARRAY_RE.search(sql)
    assert match, "RLS policy array not found in 0003_rls.sql"
    return re.findall(r"'([^']+)'", match.group(1))


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

    expected_versions = sorted(
        path.stem for path in DEFAULT_MIGRATIONS_DIR.glob("*.sql")
    )
    assert first == expected_versions
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


@pytest.mark.skipif(
    not os.getenv("GROWTH_TEST_DATABASE_URL"),
    reason="GROWTH_TEST_DATABASE_URL is not set",
)
async def test_social_tables_exist_and_status_is_constrained():
    url = os.environ["GROWTH_TEST_DATABASE_URL"]
    await apply_migrations(url)
    conn = await asyncpg.connect(url)
    try:
        tables = await conn.fetch(
            "select tablename from pg_tables where schemaname = 'public'"
        )
        names = {row["tablename"] for row in tables}
        assert {
            "growth_sources",
            "social_leads",
            "outreach_messages",
            "outreach_versions",
            "approval_requests",
            "delivery_log",
        } <= names
        tenant_id, workspace_id = uuid.uuid4(), uuid.uuid4()
        await conn.execute("insert into tenants(id, name) values($1, 't')", tenant_id)
        await conn.execute(
            "insert into workspaces(id, tenant_id, name) values($1, $2, 'w')",
            workspace_id,
            tenant_id,
        )
        with pytest.raises(asyncpg.CheckViolationError):
            await conn.execute(
                "insert into social_leads (tenant_id, workspace_id, platform, "
                "platform_post_id, source_url, dedupe_key, status) "
                "values ($1, $2, 'reddit', 'x', 'https://example.com', 'x', "
                "'not-a-status')",
                tenant_id,
                workspace_id,
            )

        policy_tables = _rls_policy_tables()
        rls_rows = await conn.fetch(
            """
            select c.relname,
                   c.relrowsecurity,
                   exists (
                       select 1
                       from pg_policies p
                       where p.schemaname = 'public'
                         and p.tablename = c.relname
                         and p.policyname = 'tenant_isolation'
                   ) as has_policy
            from pg_class c
            join pg_namespace n on n.oid = c.relnamespace
            where n.nspname = 'public'
              and c.relname = any($1::text[])
            """,
            policy_tables,
        )
        by_table = {row["relname"]: row for row in rls_rows}
        for table in policy_tables:
            assert table in by_table, f"{table} is missing"
            assert by_table[table]["relrowsecurity"] is True, f"{table} has no RLS"
            assert by_table[table]["has_policy"] is True, (
                f"{table} has no tenant_isolation policy"
            )
    finally:
        await conn.close()


async def test_apply_migrations_rejects_missing_migrations_dir(tmp_path):
    with pytest.raises(FileNotFoundError):
        await apply_migrations(
            "postgresql://unreachable", tmp_path / "does-not-exist"
        )


async def test_apply_migrations_rejects_empty_migrations_dir(tmp_path):
    with pytest.raises(ValueError):
        await apply_migrations("postgresql://unreachable", tmp_path)
