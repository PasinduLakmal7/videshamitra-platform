"""Event envelope + outbox publishing helpers."""

from __future__ import annotations

import json
import logging
from typing import Any
from uuid import UUID

import asyncpg

from app.core.config import settings
from app.core.request_id import current_trace_id
from app.events.schemas import EventEnvelope, make_event

logger = logging.getLogger(__name__)


async def enqueue_event(
    conn: asyncpg.Connection,
    *,
    event_type: str,
    data: dict[str, Any],
    stream: str,
    event_id: UUID | None = None,
    trace_id: str | None = None,
    version: int = 1,
) -> EventEnvelope:
    """Insert an outbox row inside the caller's transaction."""
    envelope = make_event(
        event_type,
        data,
        trace_id=trace_id or current_trace_id(),
        event_id=event_id,
        version=version,
    )
    await conn.execute(
        """
        insert into core.outbox_events
            (event_id, event_type, version, stream, payload)
        values ($1, $2, $3, $4, $5)
        """,
        envelope.event_id,
        envelope.event_type,
        envelope.version,
        stream,
        envelope.model_dump(mode="json"),
    )
    logger.info(
        "outbox_event_enqueued",
        extra={
            "event_id": str(envelope.event_id),
            "event_type": event_type,
            "stream": stream,
        },
    )
    return envelope


def encode_for_stream(envelope: EventEnvelope | dict[str, Any]) -> dict[str, str]:
    payload = envelope.model_dump(mode="json") if isinstance(envelope, EventEnvelope) else envelope
    return {"event": json.dumps(payload, separators=(",", ":"), default=str)}


def decode_from_stream(fields: dict[str, Any]) -> dict[str, Any]:
    raw = fields.get("event")
    if raw is None:
        return dict(fields)
    return json.loads(raw)


def dead_letter_stream(stream: str) -> str:
    return f"{stream}:dlq"


DEFAULT_STREAMS = {
    "verification.requested": settings.AI_REQUESTS_STREAM,
    "notification.requested": settings.NOTIFICATION_REQUESTS_STREAM,
}
