"""Run the notification consumer and delivery worker in one process."""

from __future__ import annotations

import asyncio
import logging

from app.core.config import settings
from app.core.logging import setup_logging
from app.db import redis as redis_db
from app.db.pool import close_pool, create_pool
from app.events.consumer import StreamConsumer, install_stop_handlers
from app.providers import build_push_provider, build_whatsapp_provider
from app.workers.delivery_worker import DeliveryWorker
from app.workers.notification_consumer import handle_event

logger = logging.getLogger(__name__)


async def main() -> None:
    setup_logging()
    await create_pool()
    client = redis_db.create_client()
    stop = asyncio.Event()
    install_stop_handlers(stop)

    consumer = StreamConsumer(
        client,
        settings.NOTIFICATION_REQUESTS_STREAM,
        settings.NOTIFICATION_CONSUMER_GROUP,
        batch=settings.NOTIFICATION_CONSUMER_BATCH,
    )
    worker = DeliveryWorker(
        push_provider=build_push_provider(),
        whatsapp_provider=build_whatsapp_provider(),
    )

    tasks = [
        asyncio.create_task(consumer.run(handle_event, stop_event=stop), name="notifications"),
        asyncio.create_task(worker.run_forever(stop), name="delivery"),
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
