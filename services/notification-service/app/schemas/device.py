"""Device registration DTOs matching core-api's proxy payload."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class DeviceRegisterRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    user_id: UUID
    token: str = Field(min_length=1, max_length=512)
    platform: Literal["android", "ios", "web"]
    app_version: str | None = Field(default=None, max_length=50)
    device_id: str | None = Field(default=None, max_length=200)
    locale: str | None = Field(default=None, max_length=8)


class DeviceOut(BaseModel):
    id: UUID
    user_id: UUID
    platform: str
    app_version: str | None = None
    device_id: str | None = None
    locale: str | None = None
    is_active: bool
    last_seen_at: str

    @classmethod
    def from_record(cls, row) -> DeviceOut:
        return cls(
            id=row["id"],
            user_id=row["user_id"],
            platform=row["platform"],
            app_version=row["app_version"],
            device_id=row["device_id"],
            locale=row["locale"],
            is_active=row["is_active"],
            last_seen_at=row["last_seen_at"].isoformat(),
        )
