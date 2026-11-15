from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path

import asyncpg

DEFAULT_MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"

_ENSURE_MIGRATIONS_TABLE = """
create table if not exists schema_migrations (
  version text primary key,
  applied_at timestamptz not null default now()
);
"""


async def apply_migrations(
    database_url: str, migrations_dir: Path | None = None
) -> list[str]:
    """Apply pending numbered SQL migrations in filename order.

    Returns the versions (file stems) applied during this call. Already
    applied versions are skipped, so repeated calls are idempotent.
    """
    directory = Path(migrations_dir) if migrations_dir else DEFAULT_MIGRATIONS_DIR
    files = sorted(directory.glob("*.sql"), key=lambda path: path.name)

    applied: list[str] = []
    conn = await asyncpg.connect(database_url)
    try:
        await conn.execute(_ENSURE_MIGRATIONS_TABLE)
        existing = {
            row["version"]
            for row in await conn.fetch("select version from schema_migrations")
        }
        for path in files:
            version = path.stem
            if version in existing:
                continue
            sql = path.read_text(encoding="utf-8")
            async with conn.transaction():
                await conn.execute(sql)
                await conn.execute(
                    "insert into schema_migrations (version) values ($1)", version
                )
            applied.append(version)
            existing.add(version)
    finally:
        await conn.close()
    return applied


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply Growth Agent migrations.")
    parser.add_argument(
        "--database-url",
        default=os.environ.get("GROWTH_DATABASE_URL", ""),
        help="Postgres DSN (defaults to GROWTH_DATABASE_URL).",
    )
    parser.add_argument(
        "--migrations-dir",
        default=None,
        help="Directory containing numbered *.sql migrations.",
    )
    args = parser.parse_args()

    if not args.database_url:
        parser.error("--database-url or GROWTH_DATABASE_URL is required")

    migrations_dir = Path(args.migrations_dir) if args.migrations_dir else None
    applied = asyncio.run(apply_migrations(args.database_url, migrations_dir))
    if applied:
        print("Applied migrations: " + ", ".join(applied))
    else:
        print("No pending migrations.")


if __name__ == "__main__":
    main()
