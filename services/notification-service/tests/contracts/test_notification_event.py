from __future__ import annotations

from pathlib import Path

import jsonschema
import pytest
from pydantic import ValidationError

from app.events.schemas import NotificationRequestedEvent

ROOT = Path(__file__).resolve().parents[4]
SCHEMA = ROOT / "packages/contracts/schemas/notification.requested.v1.schema.json"


def test_payload_matches_published_schema():
    event = NotificationRequestedEvent.model_validate(
        {
            "event_id": "0c1d1f0e-6d6a-4f4d-a6f8-2a1a6d3f6f11",
            "event_type": "notification.requested",
            "version": 1,
            "occurred_at": "2026-11-26T10:00:00Z",
            "producer": "core-api",
            "trace_id": "a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d",
            "data": {
                "notification_id": "1d2e3f40-5a6b-4c7d-8e9f-0a1b2c3d4e5f",
                "user_id": "3c4b5a69-7d8e-4f01-9234-56789abcdef0",
                "locale": "si",
                "type": "verification_complete",
                "title": "Verification complete",
                "body": "Your job offer has a high-risk finding. Tap to review.",
                "data": {"verification_id": "9e8d7c6b-5a49-4382-a1b0-c9d8e7f6a5b4"},
                "deep_link": "videshamitra://verifications/9e8d7c6b",
                "channels": ["push", "whatsapp"],
            },
        }
    )
    schema = __import__("json").loads(SCHEMA.read_text())
    jsonschema.validate(event.model_dump(mode="json"), schema)


def test_suffixed_event_type_is_not_the_contract():
    with pytest.raises(ValidationError):
        NotificationRequestedEvent.model_validate(
            {
                "event_id": "0c1d1f0e-6d6a-4f4d-a6f8-2a1a6d3f6f11",
                "event_type": "notification.requested.v1",
                "version": 1,
                "occurred_at": "2026-11-26T10:00:00Z",
                "producer": "core-api",
                "trace_id": "a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d",
                "data": {
                    "notification_id": "1d2e3f40-5a6b-4c7d-8e9f-0a1b2c3d4e5f",
                    "user_id": "3c4b5a69-7d8e-4f01-9234-56789abcdef0",
                    "type": "system",
                    "title": "t",
                    "body": "b",
                },
            }
        )
