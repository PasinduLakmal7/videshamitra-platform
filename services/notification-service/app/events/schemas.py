"""Strict models for the notification.requested event."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class EventEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: UUID
    event_type: str
    version: int = 1
    occurred_at: datetime
    producer: str
    trace_id: UUID
    data: dict[str, Any]

    @field_validator("occurred_at")
    @classmethod
    def _utc(cls, value: datetime) -> datetime:
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


class NotificationRequestedData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    notification_id: UUID
    user_id: UUID
    locale: str = "en"
    type: str
    title: str
    body: str
    data: dict[str, Any] = Field(default_factory=dict)
    deep_link: str | None = None
    channels: list[str] = Field(default_factory=lambda: ["in_app"])


class NotificationRequestedEvent(EventEnvelope):
    event_type: Literal["notification.requested"] = "notification.requested"
    data: NotificationRequestedData  # type: ignore[assignment]
