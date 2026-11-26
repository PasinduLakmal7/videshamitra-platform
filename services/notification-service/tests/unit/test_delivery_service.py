from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from app.events.schemas import NotificationRequestedData
from app.models.enums import DEFAULT_CHANNELS
from app.schemas.preference import PreferencesOut
from app.services.delivery_service import DeliveryService


class FakeDeliveries:
    def __init__(self):
        self.rows: list[dict] = []

    async def create(self, conn, **kwargs):
        self.rows.append(kwargs)
        return {"id": uuid4(), **kwargs}


class FakeDevices:
    def __init__(self, tokens):
        self.tokens = tokens

    async def list_active(self, conn, user_id):
        return self.tokens


class FakePreferences:
    def __init__(self, prefs: PreferencesOut):
        self.prefs = prefs

    async def get(self, conn, user_id):
        return self.prefs

    @staticmethod
    def channel_enabled(prefs, channel):
        return bool(prefs.channels.get(channel, False))


def _prefs(**overrides) -> PreferencesOut:
    values = {
        "user_id": uuid4(),
        "channels": dict(DEFAULT_CHANNELS),
        "quiet_hours_start": None,
        "quiet_hours_end": None,
        "timezone": "Asia/Colombo",
        "locale": "en",
    }
    values.update(overrides)
    return PreferencesOut(**values)


def _event(channels: list[str], data=None) -> NotificationRequestedData:
    return NotificationRequestedData(
        notification_id=uuid4(),
        user_id=uuid4(),
        locale="en",
        type="checkin_due",
        title="Safety check-in",
        body="How are you?",
        data=data or {},
        deep_link="videshamitra://checkins/1",
        channels=channels,
    )


async def test_push_fans_out_per_device_and_skips_unsupported():
    deliveries = FakeDeliveries()
    devices = FakeDevices([{"id": uuid4()}, {"id": uuid4()}])
    service = DeliveryService(
        deliveries=deliveries,
        devices=devices,
        preferences=FakePreferences(_prefs()),
    )
    summary = await service.enqueue(None, _event(["push", "whatsapp", "email", "in_app"]))
    assert summary["push"] == 2
    assert summary["skipped"] == 2
    push_rows = [row for row in deliveries.rows if row["channel"] == "push"]
    assert len(push_rows) == 2
    assert not [row for row in deliveries.rows if row["channel"] == "in_app"]


async def test_no_devices_creates_skipped_row():
    deliveries = FakeDeliveries()
    service = DeliveryService(
        deliveries=deliveries,
        devices=FakeDevices([]),
        preferences=FakePreferences(_prefs()),
    )
    summary = await service.enqueue(None, _event(["push"]))
    assert summary["skipped"] == 1
    assert deliveries.rows[0]["last_error_code"] == "no_device"
    assert deliveries.rows[0]["status"] == "skipped"


async def test_disabled_push_is_skipped():
    deliveries = FakeDeliveries()
    prefs = _prefs(channels={**DEFAULT_CHANNELS, "push": False})
    service = DeliveryService(
        deliveries=deliveries,
        devices=FakeDevices([{"id": uuid4()}]),
        preferences=FakePreferences(prefs),
    )
    summary = await service.enqueue(None, _event(["push"]))
    assert summary["skipped"] == 1
    assert deliveries.rows[0]["last_error_code"] == "channel_disabled"


async def test_whatsapp_without_recipient_is_skipped():
    deliveries = FakeDeliveries()
    prefs = _prefs(channels={**DEFAULT_CHANNELS, "whatsapp": True})
    service = DeliveryService(
        deliveries=deliveries,
        devices=FakeDevices([]),
        preferences=FakePreferences(prefs),
    )
    summary = await service.enqueue(None, _event(["whatsapp"]))
    assert summary["skipped"] == 1
    assert deliveries.rows[0]["last_error_code"] in {
        "provider_not_configured",
        "missing_recipient",
    }


def test_quiet_hours_timing():
    deliveries = FakeDeliveries()
    prefs = _prefs(quiet_hours_start="21:00", quiet_hours_end="07:00")
    service = DeliveryService(
        deliveries=deliveries,
        devices=FakeDevices([]),
        preferences=FakePreferences(prefs),
    )
    now = datetime(2026, 11, 26, 17, 0, tzinfo=UTC)  # 22:30 Colombo
    status, reason, next_attempt = service._timing(prefs, now)
    assert status == "pending"
    assert reason == "quiet_hours"
    assert next_attempt == datetime(2026, 11, 27, 1, 30, tzinfo=UTC)
