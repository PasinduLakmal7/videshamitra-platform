"""Preference DTOs. `PUT` is a partial upsert even though it uses PUT."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.enums import SUPPORTED_CHANNELS
from app.utils.quiet_hours import parse_hhmm


class PreferencesUpdate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    channels: dict[str, bool] | None = None
    quiet_hours_start: str | None = Field(default=None, max_length=8)
    quiet_hours_end: str | None = Field(default=None, max_length=8)
    locale: str | None = Field(default=None, max_length=8)

    @field_validator("channels")
    @classmethod
    def _known_channels(cls, value: dict[str, bool] | None) -> dict[str, bool] | None:
        if value is None:
            return None
        unknown = sorted(set(value) - SUPPORTED_CHANNELS)
        if unknown:
            raise ValueError(f"unknown channels: {', '.join(unknown)}")
        return value

    @field_validator("quiet_hours_start", "quiet_hours_end")
    @classmethod
    def _parse_time(cls, value: str | None) -> str | None:
        if value is None:
            return None
        parse_hhmm(value)
        return value

    @model_validator(mode="after")
    def _quiet_hours_pair(self) -> PreferencesUpdate:
        if (self.quiet_hours_start is None) != (self.quiet_hours_end is None):
            raise ValueError("quiet_hours_start and quiet_hours_end must be sent together")
        return self


class PreferencesOut(BaseModel):
    user_id: UUID
    channels: dict[str, bool]
    quiet_hours_start: str | None = None
    quiet_hours_end: str | None = None
    timezone: str
    locale: str | None = None

    @classmethod
    def from_record(cls, user_id: UUID, row, defaults: dict[str, bool], timezone: str):
        if row is None:
            return cls(
                user_id=user_id,
                channels=defaults,
                timezone=timezone,
            )
        start = row.get("quiet_hours_start")
        end = row.get("quiet_hours_end")
        return cls(
            user_id=user_id,
            channels={**defaults, **row.get("channels", {})},
            quiet_hours_start=start.strftime("%H:%M") if start else None,
            quiet_hours_end=end.strftime("%H:%M") if end else None,
            timezone=row.get("timezone") or timezone,
            locale=row.get("locale"),
        )
