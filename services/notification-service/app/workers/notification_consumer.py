"""Consumer handler: dedupe the event and create delivery rows."""

from __future__ import annotations

import logging

from pydantic import ValidationError

from app.core.config import settings
from app.db.pool import transaction
from app.events.envelope import InvalidEvent
from app.events.schemas import EventEnvelope, NotificationRequestedData
from app.repositories.dedupe_repository import DedupeRepository
from app.services.delivery_service import DeliveryService

logger = logging.getLogger(__name__)


async def handle_event(event: dict) -> None:
    try:
        envelope = EventEnvelope.model_validate(event)
    except ValidationError as exc:
        raise InvalidEvent("invalid notification event envelope") from exc

    if envelope.event_type != "notification.requested":
        logger.info("unknown_event_type_ignored", extra={"event_type": envelope.event_type})
        return
    if envelope.version != 1:
        logger.info(
            "unsupported_event_version_ignored",
            extra={"event_type": envelope.event_type, "version": envelope.version},
        )
        return

    try:
        data = NotificationRequestedData.model_validate(envelope.data)
    except ValidationError as exc:
        raise InvalidEvent("invalid notification data") from exc

    async with transaction() as conn:
        inserted = await DedupeRepository().try_insert(
            conn,
            consumer=settings.NOTIFICATION_CONSUMER_GROUP,
            event_id=envelope.event_id,
            event_type=envelope.event_type,
            notification_id=data.notification_id,
        )
        if not inserted:
            logger.info(
                "duplicate_event_ignored",
                extra={"event_id": str(envelope.event_id)},
            )
            return
        await DeliveryService().enqueue(conn, data)
