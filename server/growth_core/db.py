from __future__ import annotations

import asyncpg


async def create_pool(database_url: str) -> asyncpg.Pool:
    """Create an asyncpg connection pool for the Growth Agent database."""
    return await asyncpg.create_pool(database_url)
