"""In-app notification and proxy DTOs."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import NotificationType
from app.schemas.base import APIModel


class NotificationOut(APIModel):
    id: UUID
    user_id: UUID
    type: NotificationType
    title: str
    body: str
    data: dict[str, Any] = Field(default_factory=dict)
    deep_link: str | None = None
    read_at: datetime | None = None
    created_at: datetime


class DeviceRegister(BaseModel):
    token: str = Field(min_length=1, max_length=512)
    platform: str = Field(pattern="^(android|ios|web)$")
    app_version: str | None = Field(default=None, max_length=50)
    device_id: str | None = Field(default=None, max_length=200)
    locale: str | None = Field(default=None, max_length=8)


class PreferencesUpdate(BaseModel):
    channels: dict[str, bool] | None = None
    quiet_hours_start: str | None = Field(default=None, max_length=8)
    quiet_hours_end: str | None = Field(default=None, max_length=8)
    locale: str | None = Field(default=None, max_length=8)
