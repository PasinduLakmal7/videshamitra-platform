from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

from app.events.schemas import NotificationRequestedData
from app.services.delivery_service import build_push_data, stringify


def test_stringify_scalars_and_nested():
    assert stringify("hello") == "hello"
    assert stringify(True) == "true"
    assert stringify(12) == "12"
    assert stringify({"a": 1}) == '{"a":1}'
    assert stringify([1, 2]) == "[1,2]"
    assert stringify(None) is None
    assert stringify(uuid4()) is not None


def test_build_push_data_has_mobile_required_fields():
    event = NotificationRequestedData(
        notification_id=uuid4(),
        user_id=uuid4(),
        locale="si",
        type="verification_complete",
        title="Verification complete",
        body="Tap to review",
        data={
            "verification_id": uuid4(),
            "nested": {"risk": "high"},
            "count": 2,
            "phone": "+94770000000",
        },
        deep_link="videshamitra://verifications/1",
        channels=["push"],
    )
    data = build_push_data(event)
    assert data["type"] == "verification_complete"
    assert data["deep_link"] == "videshamitra://verifications/1"
    assert data["notification_id"] == str(event.notification_id)
    assert data["nested"] == '{"risk":"high"}'
    assert data["count"] == "2"
    assert "phone" not in data
    assert all(isinstance(value, str) for value in data.values())


def test_backoff_is_bounded(monkeypatch):
    from app.workers import delivery_worker

    monkeypatch.setattr(delivery_worker.random, "uniform", lambda low, high: high)
    first = delivery_worker.backoff_delay(1)
    capped = delivery_worker.backoff_delay(20)
    assert first <= timedelta(seconds=30)
    assert capped <= timedelta(seconds=3600)


def test_backoff_honours_retry_after(monkeypatch):
    from app.workers import delivery_worker

    monkeypatch.setattr(delivery_worker.random, "uniform", lambda low, high: 0)
    assert delivery_worker.backoff_delay(1, retry_after=120) == timedelta(seconds=120)
