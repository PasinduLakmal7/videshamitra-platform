"""Turn notification events into delivery rows and build provider payloads."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import asyncpg

from app.core.config import settings
from app.events.schemas import NotificationRequestedData
from app.models.enums import DeliveryChannel, DeliveryStatus
from app.repositories.delivery_repository import DeliveryRepository
from app.repositories.device_repository import DeviceRepository
from app.services.preference_service import PreferenceService
from app.utils.quiet_hours import is_quiet, next_quiet_end

logger = logging.getLogger(__name__)

_UNSUPPORTED = {DeliveryChannel.EMAIL.value, DeliveryChannel.SMS.value}


def stringify(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, (dict, list)):
        return json.dumps(value, separators=(",", ":"), default=str)
    return str(value)


def build_push_data(event: NotificationRequestedData) -> dict[str, str]:
    return _build_push_data(
        notification_type=event.type,
        notification_id=event.notification_id,
        payload=event.data,
        deep_link=event.deep_link,
    )


def build_push_data_from_delivery(row) -> dict[str, str]:
    return _build_push_data(
        notification_type=row["notification_type"],
        notification_id=row["notification_id"],
        payload=row["payload"],
        deep_link=row["deep_link"],
    )


def _build_push_data(
    *,
    notification_type: str,
    notification_id: UUID,
    payload: dict[str, Any],
    deep_link: str | None,
) -> dict[str, str]:
    data = {
        key: value
        for key, raw in payload.items()
        if key != "phone" and (value := stringify(raw)) is not None
    }
    data["type"] = notification_type
    data["notification_id"] = str(notification_id)
    if deep_link:
        data["deep_link"] = deep_link
    return data


class DeliveryService:
    def __init__(
        self,
        deliveries: DeliveryRepository | None = None,
        devices: DeviceRepository | None = None,
        preferences: PreferenceService | None = None,
    ) -> None:
        self.deliveries = deliveries or DeliveryRepository()
        self.devices = devices or DeviceRepository()
        self.preferences = preferences or PreferenceService()

    def _timing(self, prefs, now: datetime) -> tuple[str, str, datetime]:
        start = prefs.quiet_hours_start
        end = prefs.quiet_hours_end
        start_time = datetime.strptime(start, "%H:%M").time() if isinstance(start, str) else start
        end_time = datetime.strptime(end, "%H:%M").time() if isinstance(end, str) else end
        if is_quiet(now, start_time, end_time, prefs.timezone):
            return (
                DeliveryStatus.PENDING.value,
                "quiet_hours",
                next_quiet_end(now, start_time, end_time, prefs.timezone),
            )
        return DeliveryStatus.PENDING.value, "new", now

    async def _create(
        self,
        conn: asyncpg.Connection,
        event: NotificationRequestedData,
        *,
        channel: str,
        device_token_id: UUID | None,
        status: str,
        pending_reason: str | None,
        next_attempt_at: datetime,
        last_error_code: str | None = None,
    ):
        return await self.deliveries.create(
            conn,
            notification_id=event.notification_id,
            user_id=event.user_id,
            notification_type=event.type,
            locale=event.locale,
            title=event.title,
            body=event.body,
            deep_link=event.deep_link,
            payload=event.data,
            channel=channel,
            device_token_id=device_token_id,
            status=status,
            pending_reason=pending_reason,
            next_attempt_at=next_attempt_at,
            last_error_code=last_error_code,
        )

    async def enqueue(
        self, conn: asyncpg.Connection, event: NotificationRequestedData
    ) -> dict[str, int]:
        prefs = await self.preferences.get(conn, event.user_id)
        now = datetime.now(UTC)
        status, reason, next_attempt = self._timing(prefs, now)
        summary: dict[str, int] = {}
        requested: list[str] = []
        for channel in event.channels:
            if channel in ("in_app", "push", "whatsapp", "email", "sms"):
                if channel not in requested:
                    requested.append(channel)

        for channel in requested:
            if channel == DeliveryChannel.PUSH.value:
                if not self.preferences.channel_enabled(prefs, channel):
                    await self._create(
                        conn,
                        event,
                        channel=channel,
                        device_token_id=None,
                        status=DeliveryStatus.SKIPPED.value,
                        pending_reason=None,
                        next_attempt_at=now,
                        last_error_code="channel_disabled",
                    )
                    summary["skipped"] = summary.get("skipped", 0) + 1
                    continue
                tokens = await self.devices.list_active(conn, event.user_id)
                if not tokens:
                    await self._create(
                        conn,
                        event,
                        channel=channel,
                        device_token_id=None,
                        status=DeliveryStatus.SKIPPED.value,
                        pending_reason=None,
                        next_attempt_at=now,
                        last_error_code="no_device",
                    )
                    summary["skipped"] = summary.get("skipped", 0) + 1
                    continue
                for token in tokens:
                    row = await self._create(
                        conn,
                        event,
                        channel=channel,
                        device_token_id=token["id"],
                        status=status,
                        pending_reason=reason,
                        next_attempt_at=next_attempt,
                    )
                    if row is not None:
                        summary[channel] = summary.get(channel, 0) + 1
                continue

            if channel == DeliveryChannel.WHATSAPP.value:
                if not self.preferences.channel_enabled(prefs, channel):
                    reason_code = "channel_disabled"
                elif not settings.WHATSAPP_ENABLED:
                    reason_code = "provider_not_configured"
                elif not str(event.data.get("phone") or "").strip():
                    reason_code = "missing_recipient"
                else:
                    reason_code = None
                if reason_code:
                    await self._create(
                        conn,
                        event,
                        channel=channel,
                        device_token_id=None,
                        status=DeliveryStatus.SKIPPED.value,
                        pending_reason=None,
                        next_attempt_at=now,
                        last_error_code=reason_code,
                    )
                    summary["skipped"] = summary.get("skipped", 0) + 1
                else:
                    row = await self._create(
                        conn,
                        event,
                        channel=channel,
                        device_token_id=None,
                        status=status,
                        pending_reason=reason,
                        next_attempt_at=next_attempt,
                    )
                    if row is not None:
                        summary[channel] = summary.get(channel, 0) + 1
                continue

            if channel in _UNSUPPORTED:
                await self._create(
                    conn,
                    event,
                    channel=channel,
                    device_token_id=None,
                    status=DeliveryStatus.SKIPPED.value,
                    pending_reason=None,
                    next_attempt_at=now,
                    last_error_code="unsupported_channel",
                )
                summary["skipped"] = summary.get("skipped", 0) + 1
                continue

        logger.info(
            "deliveries_enqueued",
            extra={
                "notification_id": str(event.notification_id),
                "user_id": str(event.user_id),
                "channels": requested,
                "counts": summary,
            },
        )
        return summary
