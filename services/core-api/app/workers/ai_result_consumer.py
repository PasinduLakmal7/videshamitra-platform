"""Consume verification results from ai-service, exactly once per event."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.core.config import settings
from app.core.logging import setup_logging
from app.db import redis as redis_db
from app.db.pool import acquire, close_pool, create_pool
from app.events.consumer import StreamConsumer, install_stop_handlers
from app.events.publisher import mark_processed
from app.services.verification_service import VerificationService

logger = logging.getLogger(__name__)

CONSUMER = "core-api"


async def handle_event(event: dict[str, Any]) -> None:
    event_id = event.get("event_id")
    if not event_id:
        logger.warning("event_missing_id")
        return
    async with acquire() as conn:
        async with conn.transaction():
            fresh = await mark_processed(conn, CONSUMER, event_id)
            if not fresh:
                logger.info("event_duplicate_ignored", extra={"event_id": event_id})
                return
            await VerificationService().handle_result(conn, event)


async def main() -> None:
    setup_logging()
    await create_pool()
    client = redis_db.create_client()
    stop = asyncio.Event()
    install_stop_handlers(stop)
    consumer = StreamConsumer(
        client,
        settings.AI_RESULTS_STREAM,
        settings.AI_CONSUMER_GROUP,
    )
    try:
        await consumer.run(handle_event, stop_event=stop)
    finally:
        await redis_db.close_client()
        await close_pool()


if __name__ == "__main__":
    asyncio.run(main())
