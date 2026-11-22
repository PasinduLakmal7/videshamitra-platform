"""Outbox publisher/relay and DB-backed consumer dedupe."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID

import asyncpg

from app.core.config import settings
from app.db import redis as redis_db
from app.events.envelope import dead_letter_stream, encode_for_stream

logger = logging.getLogger(__name__)


async def mark_processed(conn: asyncpg.Connection, consumer: str, event_id: UUID | str) -> bool:
    """Insert a dedupe row. Returns False when the event was already handled."""
    row = await conn.fetchval(
        """
        insert into core.event_dedupe (consumer, event_id)
        values ($1, $2)
        on conflict (consumer, event_id) do nothing
        returning id
        """,
        consumer,
        event_id,
    )
    return row is not None


async def relay_once(limit: int | None = None) -> int:
    """Publish one batch of pending outbox rows. Safe to run concurrently."""
    limit = limit or settings.OUTBOX_BATCH_SIZE
    client = redis_db.get_client()
    published = 0
    from app.db.pool import acquire

    async with acquire() as conn:
        async with conn.transaction():
            rows = await conn.fetch(
                """
                select id, event_id, event_type, stream, payload, attempts
                from core.outbox_events
                where status = 'pending' and available_at <= now()
                order by created_at
                limit $1
                for update skip locked
                """,
                limit,
            )
            for row in rows:
                payload = row["payload"]
                if isinstance(payload, str):
                    payload = json.loads(payload)
                try:
                    await client.xadd(
                        row["stream"],
                        encode_for_stream(payload),
                        maxlen=settings.EVENT_MAX_LENGTH,
                    )
                except Exception as exc:
                    attempts = row["attempts"] + 1
                    failed = attempts >= settings.OUTBOX_MAX_ATTEMPTS
                    backoff = min(2**attempts, 300)
                    if failed:
                        await client.xadd(
                            dead_letter_stream(row["stream"]),
                            {
                                "event": json.dumps(payload, default=str),
                                "error": "outbox_exhausted",
                            },
                            maxlen=settings.EVENT_MAX_LENGTH,
                        )
                    await conn.execute(
                        """
                        update core.outbox_events
                        set status = $2,
                            attempts = $3,
                            available_at = $4,
                            last_error = $5
                        where id = $1
                        """,
                        row["id"],
                        "failed" if failed else "pending",
                        attempts,
                        datetime.now(UTC) + timedelta(seconds=backoff),
                        str(exc)[:1000],
                    )
                    logger.error(
                        "outbox_publish_failed",
                        extra={
                            "event_id": str(row["event_id"]),
                            "attempts": attempts,
                            "dead_letter": failed,
                        },
                    )
                    continue

                await conn.execute(
                    """
                    update core.outbox_events
                    set status = 'published', attempts = attempts + 1, published_at = now()
                    where id = $1
                    """,
                    row["id"],
                )
                published += 1
                logger.info(
                    "outbox_event_published",
                    extra={
                        "event_id": str(row["event_id"]),
                        "event_type": row["event_type"],
                        "stream": row["stream"],
                    },
                )
    return published


async def run_relay(stop_event: asyncio.Event, interval: float = 0.5) -> None:
    logger.info("outbox_relay_started")
    while not stop_event.is_set():
        try:
            await relay_once()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("outbox_relay_failed")
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval)
        except TimeoutError:
            pass
    logger.info("outbox_relay_stopped")
