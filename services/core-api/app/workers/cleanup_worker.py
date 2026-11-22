"""Periodic cleanup of expired idempotency reservations."""

from __future__ import annotations

import asyncio
import logging

from app.core.idempotency import cleanup_expired
from app.core.logging import setup_logging
from app.db.pool import acquire, close_pool, create_pool

logger = logging.getLogger(__name__)


async def run_once() -> int:
    async with acquire() as conn:
        removed = await cleanup_expired(conn)
    if removed:
        logger.info("idempotency_keys_cleaned", extra={"count": removed})
    return removed


async def main() -> None:
    setup_logging()
    await create_pool()
    try:
        while True:
            try:
                await run_once()
            except Exception:
                logger.exception("idempotency_cleanup_failed")
            await asyncio.sleep(3600)
    finally:
        await close_pool()


if __name__ == "__main__":
    asyncio.run(main())
