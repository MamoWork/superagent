from __future__ import annotations

import argparse
import asyncio
import os
import sys
import uuid

import asyncpg

from growth_core.seed_data import seed_tenant

__all__ = ["main", "seed_tenant"]


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Seed a Growth Agent tenant with default configuration."
    )
    parser.add_argument("--tenant-id", required=True, type=uuid.UUID)
    parser.add_argument("--workspace-id", required=True, type=uuid.UUID)
    parser.add_argument("--tenant-name", default="Default")
    parser.add_argument("--workspace-name", default="Default")
    parser.add_argument(
        "--database-url",
        default=os.environ.get("GROWTH_DATABASE_URL", ""),
        help="Postgres DSN (defaults to GROWTH_DATABASE_URL).",
    )
    args = parser.parse_args(argv)

    if not args.database_url:
        parser.error("--database-url or GROWTH_DATABASE_URL is required")
    return args


async def _seed(args: argparse.Namespace) -> None:
    conn = await asyncpg.connect(args.database_url)
    try:
        await seed_tenant(
            conn,
            tenant_id=args.tenant_id,
            workspace_id=args.workspace_id,
            tenant_name=args.tenant_name,
            workspace_name=args.workspace_name,
        )
    finally:
        await conn.close()


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    try:
        asyncio.run(_seed(args))
    except asyncpg.UndefinedTableError as exc:
        print(
            "error: growth tables are missing; run "
            "`python -m growth_core.migrate` first",
            file=sys.stderr,
        )
        raise SystemExit(1) from exc
    except asyncpg.UndefinedColumnError as exc:
        print(
            "error: database schema is out of date; run "
            "`python -m growth_core.migrate` first",
            file=sys.stderr,
        )
        raise SystemExit(1) from exc

    print(f"Seeded tenant {args.tenant_id} and workspace {args.workspace_id}.")


if __name__ == "__main__":
    main()
