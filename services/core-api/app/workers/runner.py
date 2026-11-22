"""Run every core-api background loop in one worker process."""

from __future__ import annotations

import asyncio
import logging

from app.core.config import settings
from app.core.logging import setup_logging
from app.db import redis as redis_db
from app.db.pool import close_pool, create_pool
from app.events.consumer import StreamConsumer, install_stop_handlers
from app.events.publisher import run_relay
from app.workers import agency_monitor, checkin_worker, cleanup_worker
from app.workers.ai_result_consumer import handle_event

logger = logging.getLogger(__name__)


async def main() -> None:
    setup_logging()
    await create_pool()
    client = redis_db.create_client()
    stop = asyncio.Event()
    install_stop_handlers(stop)
    consumer = StreamConsumer(client, settings.AI_RESULTS_STREAM, settings.AI_CONSUMER_GROUP)

    async def checkin_loop() -> None:
        while not stop.is_set():
            await checkin_worker.run_once()
            try:
                await asyncio.wait_for(
                    stop.wait(), timeout=settings.CHECKIN_SCHEDULER_INTERVAL_SECONDS
                )
            except TimeoutError:
                pass

    async def agency_loop() -> None:
        while not stop.is_set():
            try:
                await agency_monitor.run_once()
            except Exception:
                logger.exception("agency_monitor_failed")
            try:
                await asyncio.wait_for(
                    stop.wait(), timeout=settings.AGENCY_MONITOR_INTERVAL_SECONDS
                )
            except TimeoutError:
                pass

    async def cleanup_loop() -> None:
        while not stop.is_set():
            try:
                await cleanup_worker.run_once()
            except Exception:
                logger.exception("idempotency_cleanup_failed")
            try:
                await asyncio.wait_for(stop.wait(), timeout=3600)
            except TimeoutError:
                pass

    tasks = [
        asyncio.create_task(run_relay(stop), name="outbox-relay"),
        asyncio.create_task(consumer.run(handle_event, stop_event=stop), name="ai-results"),
        asyncio.create_task(checkin_loop(), name="checkins"),
        asyncio.create_task(agency_loop(), name="agency-monitor"),
        asyncio.create_task(cleanup_loop(), name="cleanup"),
    ]
    try:
        await asyncio.gather(*tasks)
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await redis_db.close_client()
        await close_pool()
        logger.info("worker_stopped")


if __name__ == "__main__":
    asyncio.run(main())
