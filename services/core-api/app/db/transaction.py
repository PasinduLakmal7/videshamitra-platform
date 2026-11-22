"""Transaction helper re-exported for services that own their connections."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import asyncpg

from app.db.pool import acquire


@asynccontextmanager
async def transaction(conn: asyncpg.Connection | None = None) -> AsyncIterator[asyncpg.Connection]:
    """Use an existing connection or acquire a fresh one, inside a transaction."""
    if conn is not None:
        async with conn.transaction():
            yield conn
        return
    async with acquire() as new_conn:
        async with new_conn.transaction():
            yield new_conn
