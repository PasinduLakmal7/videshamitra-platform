"""Delivery worker: claim rows, send, record attempts, retry/defer."""

from __future__ import annotations

import asyncio
import logging
import random
from datetime import UTC, datetime, timedelta

from app.core.config import settings
from app.db.pool import acquire, transaction
from app.models.enums import AttemptStatus, DeliveryChannel
from app.providers.base import (
    DeliveryResult,
    PushMessage,
    PushProvider,
    WhatsAppMessage,
    WhatsAppProviderProtocol,
)
from app.repositories.delivery_repository import DeliveryRepository
from app.repositories.device_repository import DeviceRepository
from app.services.delivery_service import build_push_data_from_delivery

logger = logging.getLogger(__name__)


def backoff_delay(attempt: int, retry_after: int | None = None) -> timedelta:
    base = min(
        settings.DELIVERY_BASE_BACKOFF_SECONDS * (2 ** max(0, attempt - 1)),
        settings.DELIVERY_MAX_BACKOFF_SECONDS,
    )
    if retry_after is not None:
        base = max(base, retry_after)
    delay = random.uniform(0, base)
    if retry_after is not None:
        delay = max(delay, retry_after)
    return timedelta(seconds=delay)


class DeliveryWorker:
    def __init__(
        self,
        *,
        push_provider: PushProvider,
        whatsapp_provider: WhatsAppProviderProtocol | None = None,
        deliveries: DeliveryRepository | None = None,
        devices: DeviceRepository | None = None,
    ) -> None:
        self.push_provider = push_provider
        self.whatsapp_provider = whatsapp_provider
        self.deliveries = deliveries or DeliveryRepository()
        self.devices = devices or DeviceRepository()

    async def _record_result(self, delivery, result: DeliveryResult, attempt: int) -> None:
        async with transaction() as conn:
            await self.deliveries.record_attempt(
                conn,
                delivery_id=delivery["id"],
                attempt_number=attempt,
                provider=(
                    self.push_provider.name
                    if delivery["channel"] == DeliveryChannel.PUSH.value
                    else "whatsapp"
                ),
                status=(
                    AttemptStatus.SENT.value
                    if result.success
                    else (
                        AttemptStatus.RETRYABLE.value
                        if result.retryable
                        else AttemptStatus.PERMANENT.value
                    )
                ),
                http_status=result.http_status,
                provider_message_id=result.provider_message_id,
                error_code=result.error_code,
                error_message=result.error_message,
            )
            if result.success:
                await self.deliveries.mark_sent(
                    conn,
                    delivery_id=delivery["id"],
                    attempt_count=attempt,
                    provider_message_id=result.provider_message_id,
                )
            elif result.invalid_token:
                if delivery["device_token_id"] is not None:
                    await self.devices.deactivate_by_id(conn, delivery["device_token_id"])
                await self.deliveries.mark_failed(
                    conn,
                    delivery_id=delivery["id"],
                    attempt_count=attempt,
                    error_code=result.error_code or "invalid_token",
                    error_message=result.error_message,
                )
            elif result.retryable and attempt < settings.DELIVERY_MAX_ATTEMPTS:
                delay = backoff_delay(attempt, result.retry_after_seconds)
                await self.deliveries.mark_retry(
                    conn,
                    delivery_id=delivery["id"],
                    attempt_count=attempt,
                    next_attempt_at=datetime.now(UTC) + delay,
                    error_code=result.error_code,
                    error_message=result.error_message,
                )
            else:
                await self.deliveries.mark_failed(
                    conn,
                    delivery_id=delivery["id"],
                    attempt_count=attempt,
                    error_code=(
                        result.error_code
                        if result.error_code
                        else ("max_attempts" if result.retryable else "provider_rejected")
                    ),
                    error_message=result.error_message,
                )

    async def _deliver(self, delivery) -> None:
        attempt = int(delivery["attempt_count"]) + 1
        if delivery["channel"] == DeliveryChannel.PUSH.value:
            if delivery["device_token_id"] is None:
                await self._mark_no_target(delivery, "no_device")
                return
            async with acquire() as conn:
                device = await self.devices.get_by_id(conn, delivery["device_token_id"])
            if device is None or not device["is_active"]:
                await self._mark_no_target(delivery, "no_device")
                return
            message = PushMessage(
                token=device["token"],
                title=delivery["title"],
                body=delivery["body"],
                data=build_push_data_from_delivery(delivery),
                notification_id=str(delivery["notification_id"]),
            )
            result = await self.push_provider.send(message)
        elif delivery["channel"] == DeliveryChannel.WHATSAPP.value:
            if self.whatsapp_provider is None:
                await self._mark_no_target(delivery, "provider_not_configured")
                return
            recipient = str((delivery["payload"] or {}).get("phone") or "").strip()
            if not recipient:
                await self._mark_no_target(delivery, "missing_recipient")
                return
            result = await self.whatsapp_provider.send(
                WhatsAppMessage(
                    recipient=recipient,
                    title=delivery["title"],
                    body=delivery["body"],
                    locale=delivery["locale"],
                    notification_id=str(delivery["notification_id"]),
                )
            )
        else:
            await self._mark_no_target(delivery, "unsupported_channel")
            return

        await self._record_result(delivery, result, attempt)
        logger.info(
            "delivery_attempt",
            extra={
                "delivery_id": str(delivery["id"]),
                "channel": delivery["channel"],
                "attempt": attempt,
                "success": result.success,
                "retryable": result.retryable,
                "error_code": result.error_code,
            },
        )

    async def _mark_no_target(self, delivery, code: str) -> None:
        async with transaction() as conn:
            await self.deliveries.mark_failed(
                conn,
                delivery_id=delivery["id"],
                attempt_count=int(delivery["attempt_count"]),
                error_code=code,
                error_message=code,
            )
        logger.warning(
            "delivery_no_target",
            extra={"delivery_id": str(delivery["id"]), "code": code},
        )

    async def run_once(self) -> int:
        async with acquire() as conn:
            stale = await self.deliveries.reset_stale_sending(
                conn, settings.SENDING_TIMEOUT_SECONDS
            )
            if stale:
                logger.warning("stale_sending_recovered", extra={"count": stale})
            rows = await self.deliveries.claim_due(conn, settings.DELIVERY_BATCH_SIZE)
        for row in rows:
            try:
                await self._deliver(row)
            except Exception:
                logger.exception("delivery_failed", extra={"delivery_id": str(row["id"])})
        return len(rows)

    async def run_forever(self, stop_event: asyncio.Event) -> None:
        logger.info("delivery_worker_started")
        try:
            while not stop_event.is_set():
                try:
                    await self.run_once()
                except Exception:
                    logger.exception("delivery_loop_failed")
                try:
                    await asyncio.wait_for(
                        stop_event.wait(), timeout=settings.DELIVERY_POLL_INTERVAL_SECONDS
                    )
                except TimeoutError:
                    pass
        finally:
            await self.close()
            logger.info("delivery_worker_stopped")

    async def close(self) -> None:
        await self.push_provider.aclose()
        if self.whatsapp_provider is not None:
            await self.whatsapp_provider.aclose()
