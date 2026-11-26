"""Encode/decode helpers for Redis Stream event envelopes."""

from __future__ import annotations

import json
from typing import Any

from app.events.schemas import NotificationRequestedEvent


class InvalidEvent(ValueError):
    """A stream message could not be parsed as a known, valid event."""


def decode_from_stream(fields: dict[str, Any]) -> dict[str, Any]:
    raw = fields.get("event")
    if raw is None:
        return dict(fields)
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise InvalidEvent("event payload must be an object")
    return payload


def parse_notification_event(event: dict[str, Any]) -> NotificationRequestedEvent:
    return NotificationRequestedEvent.model_validate(event)


def dead_letter_stream(stream: str, suffix: str = ":dlq") -> str:
    return f"{stream}{suffix}"
