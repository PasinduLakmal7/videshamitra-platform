"""asyncpg pool for the notification schema (runtime role only)."""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import asyncpg

from app.core.config import settings

logger = logging.getLogger(__name__)

_pool: asyncpg.Pool | None = None


def _json_encoder(value: Any) -> str:
    return json.dumps(value, default=str)


async def _init_connection(conn: asyncpg.Connection) -> None:
    for name in ("jsonb", "json"):
        await conn.set_type_codec(
            name, encoder=_json_encoder, decoder=json.loads, schema="pg_catalog"
        )


async def create_pool(dsn: str | None = None) -> asyncpg.Pool:
    global _pool
    if _pool is not None:
        return _pool
    dsn = dsn or settings.DATABASE_URL
    if not dsn:
        raise RuntimeError("DATABASE_URL is not set (notification_service_role DSN)")
    logger.info("creating_database_pool")
    _pool = await asyncpg.create_pool(
        dsn=dsn,
        min_size=settings.DATABASE_MIN_POOL,
        max_size=settings.DATABASE_MAX_POOL,
        command_timeout=settings.DATABASE_COMMAND_TIMEOUT,
        server_settings={"search_path": "notification"},
        init=_init_connection,
    )
    return _pool


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
    async with acquire() as conn, conn.transaction():
        yield conn


async def get_connection() -> AsyncIterator[asyncpg.Connection]:
    async with acquire() as conn:
        yield conn


async def ping() -> bool:
    try:
        async with acquire() as conn:
            await conn.fetchval("select 1")
        return True
    except Exception:  # pragma: no cover - exercised by readiness failures
        logger.exception("database_ping_failed")
        return False
