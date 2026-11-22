"""asyncpg pool lifecycle and request-scoped connections."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import asyncpg

from app.core.config import settings

logger = logging.getLogger(__name__)

_pool: asyncpg.Pool | None = None


async def _init_connection(conn: asyncpg.Connection) -> None:
    # Store timestamps as aware UTC datetimes; JSON/JSONB as text to avoid a
    # per-row codec round trip.
    await conn.set_type_codec(
        "jsonb",
        encoder=_json_encoder,
        decoder=_json_decoder,
        schema="pg_catalog",
    )
    await conn.set_type_codec(
        "json",
        encoder=_json_encoder,
        decoder=_json_decoder,
        schema="pg_catalog",
    )


def _json_encoder(value):  # type: ignore[no-untyped-def]
    import json

    return json.dumps(value, default=str)


def _json_decoder(value):  # type: ignore[no-untyped-def]
    import json

    return json.loads(value)


async def create_pool() -> asyncpg.Pool:
    global _pool
    if _pool is not None:
        return _pool
    logger.info("creating_database_pool")
    _pool = await asyncpg.create_pool(
        dsn=settings.DATABASE_URL,
        min_size=settings.DATABASE_MIN_POOL,
        max_size=settings.DATABASE_MAX_POOL,
        command_timeout=settings.DATABASE_COMMAND_TIMEOUT,
        init=_init_connection,
    )
    return _pool


async def connect(dsn: str | None = None) -> asyncpg.Connection:
    """Open a single connection with the same JSON codecs as the pool."""
    conn = await asyncpg.connect(dsn or settings.DATABASE_URL)
    await _init_connection(conn)
    return conn


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
        logger.info("database_pool_closed")


def get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("Database pool is not initialised")
    return _pool


@asynccontextmanager
async def acquire() -> AsyncIterator[asyncpg.Connection]:
    async with get_pool().acquire() as conn:
        yield conn


@asynccontextmanager
async def transaction() -> AsyncIterator[asyncpg.Connection]:
    async with acquire() as conn:
        async with conn.transaction():
            yield conn


async def get_connection() -> AsyncIterator[asyncpg.Connection]:
    """FastAPI dependency: one connection per request."""
    async with get_pool().acquire() as conn:
        yield conn


async def ping() -> bool:
    try:
        async with acquire() as conn:
            await conn.fetchval("select 1")
        return True
    except Exception:  # pragma: no cover - exercised by readiness failures
        logger.exception("database_ping_failed")
        return False
