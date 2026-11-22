"""Redis client lifecycle (streams + lightweight rate limiting)."""

from __future__ import annotations

import logging

import redis.asyncio as redis

from app.core.config import settings

logger = logging.getLogger(__name__)

_client: redis.Redis | None = None


def create_client() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
            socket_connect_timeout=3,
            socket_timeout=5,
            health_check_interval=30,
        )
    return _client


def get_client() -> redis.Redis:
    if _client is None:
        return create_client()
    return _client


async def close_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
        logger.info("redis_client_closed")


async def ping() -> bool:
    try:
        return bool(await get_client().ping())
    except Exception:  # pragma: no cover - exercised by readiness failures
        logger.exception("redis_ping_failed")
        return False
