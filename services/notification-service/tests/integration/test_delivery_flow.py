from __future__ import annotations

import os
from uuid import uuid4

import pytest

from app.db.pool import close_pool, create_pool, transaction
from app.events.envelope import InvalidEvent
from app.events.schemas import NotificationRequestedData
from app.providers.stub import StubPushProvider
from app.repositories.device_repository import DeviceRepository
from app.workers.delivery_worker import DeliveryWorker
from app.workers.notification_consumer import handle_event

TEST_DSN = os.environ.get("TEST_DATABASE_URL", "")
pytestmark = pytest.mark.skipif(not TEST_DSN, reason="TEST_DATABASE_URL is not set")


def _event(user_id, notification_id):
    data = NotificationRequestedData(
        notification_id=notification_id,
        user_id=user_id,
        locale="en",
        type="checkin_due",
        title="Safety check-in",
        body="How are you?",
        data={"checkin_id": str(uuid4())},
        deep_link="videshamitra://checkins/1",
        channels=["push"],
    )
    return {
        "event_id": uuid4(),
        "event_type": "notification.requested",
        "version": 1,
        "occurred_at": "2026-11-26T10:00:00Z",
        "producer": "core-api",
        "trace_id": uuid4(),
        "data": data.model_dump(mode="json"),
    }


async def test_event_to_delivery_is_duplicate_safe():
    await create_pool(TEST_DSN)
    try:
        user_id = uuid4()
        notification_id = uuid4()
        async with transaction() as conn:
            await DeviceRepository().upsert(
                conn,
                user_id=user_id,
                token=f"fcm-{uuid4()}",
                platform="android",
                app_version="1.0",
                device_id="device-1",
                locale="en",
            )
        event = _event(user_id, notification_id)
        await handle_event(event)
        async with transaction() as conn:
            first = await conn.fetch(
                "select * from notification.deliveries where notification_id = $1",
                notification_id,
            )
        await handle_event(event)
        async with transaction() as conn:
            second = await conn.fetch(
                "select * from notification.deliveries where notification_id = $1",
                notification_id,
            )
        assert len(first) == 1
        assert len(second) == 1

        worker = DeliveryWorker(push_provider=StubPushProvider())
        await worker.run_once()
        async with transaction() as conn:
            row = await conn.fetchrow(
                "select * from notification.deliveries where notification_id = $1",
                notification_id,
            )
            attempts = await conn.fetch(
                "select * from notification.delivery_attempts where delivery_id = $1",
                row["id"],
            )
        assert row["status"] == "sent"
        assert row["attempt_count"] == 1
        assert len(attempts) == 1
        assert attempts[0]["status"] == "sent"
        await worker.close()
    finally:
        await close_pool()


async def test_invalid_event_does_not_create_rows():
    await create_pool(TEST_DSN)
    try:
        event = _event(uuid4(), uuid4())
        event["data"] = {"notification_id": "not-a-uuid"}
        with pytest.raises(InvalidEvent):
            await handle_event(event)
    finally:
        await close_pool()


async def test_invalid_token_is_deactivated():
    await create_pool(TEST_DSN)
    try:
        user_id = uuid4()
        notification_id = uuid4()
        token = f"fcm-invalid-{uuid4()}"
        async with transaction() as conn:
            device = await DeviceRepository().upsert(
                conn,
                user_id=user_id,
                token=token,
                platform="android",
                app_version="1.0",
                device_id="device-invalid",
                locale="en",
            )
        await handle_event(_event(user_id, notification_id))
        worker = DeliveryWorker(push_provider=StubPushProvider("invalid_token"))
        await worker.run_once()
        async with transaction() as conn:
            delivery = await conn.fetchrow(
                "select * from notification.deliveries where notification_id = $1",
                notification_id,
            )
            device_after = await conn.fetchrow(
                "select * from notification.device_tokens where id = $1", device["id"]
            )
        assert delivery["status"] == "failed"
        assert delivery["last_error_code"] == "device_unregistered"
        assert device_after["is_active"] is False
        await worker.close()
    finally:
        await close_pool()
