from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.events.envelope import InvalidEvent
from app.events.schemas import EventEnvelope, NotificationRequestedData
from app.workers import notification_consumer


def _event(event_type: str = "notification.requested", **data_overrides):
    data = {
        "notification_id": uuid4(),
        "user_id": uuid4(),
        "locale": "en",
        "type": "checkin_due",
        "title": "Safety check-in",
        "body": "How are you?",
        "data": {},
        "deep_link": None,
        "channels": ["push"],
    }
    data.update(data_overrides)
    return {
        "event_id": uuid4(),
        "event_type": event_type,
        "version": 1,
        "occurred_at": "2026-11-26T10:00:00Z",
        "producer": "core-api",
        "trace_id": uuid4(),
        "data": data,
    }


def test_event_envelope_is_strict():
    payload = _event()
    payload["extra"] = "nope"
    with pytest.raises(ValidationError):
        EventEnvelope.model_validate(payload)


def test_event_data_is_strict():
    with pytest.raises(ValidationError):
        NotificationRequestedData.model_validate(
            {
                "notification_id": uuid4(),
                "user_id": uuid4(),
                "type": "checkin_due",
                "title": "t",
                "body": "b",
                "unknown": True,
            }
        )


async def test_unknown_event_type_is_ignored(monkeypatch):
    enqueued: list = []

    async def fake_enqueue(self, conn, event):
        enqueued.append(event)

    monkeypatch.setattr(notification_consumer.DeliveryService, "enqueue", fake_enqueue)
    await notification_consumer.handle_event(_event(event_type="something.else"))
    assert enqueued == []


async def test_malformed_event_raises_invalid():
    payload = _event()
    payload["data"] = {"notification_id": "not-a-uuid"}
    with pytest.raises(InvalidEvent):
        await notification_consumer.handle_event(payload)


async def test_duplicate_event_does_not_enqueue(monkeypatch):
    from contextlib import asynccontextmanager

    enqueued: list = []

    @asynccontextmanager
    async def fake_transaction():
        yield object()

    async def fake_try_insert(self, conn, **kwargs):
        return False

    async def fake_enqueue(self, conn, event):
        enqueued.append(event)

    monkeypatch.setattr(notification_consumer, "transaction", fake_transaction)
    monkeypatch.setattr(notification_consumer.DedupeRepository, "try_insert", fake_try_insert)
    monkeypatch.setattr(notification_consumer.DeliveryService, "enqueue", fake_enqueue)
    await notification_consumer.handle_event(_event())
    assert enqueued == []
