"""Preference defaults and partial updates."""

from __future__ import annotations

from datetime import time
from uuid import UUID

import asyncpg

from app.core.config import settings
from app.models.enums import DEFAULT_CHANNELS
from app.repositories.preference_repository import PreferenceRepository
from app.schemas.preference import PreferencesOut, PreferencesUpdate
from app.utils.quiet_hours import parse_hhmm


class PreferenceService:
    def __init__(self, repo: PreferenceRepository | None = None) -> None:
        self.repo = repo or PreferenceRepository()

    def _timezone(self, row) -> str:
        return row["timezone"] if row is not None else settings.QUIET_HOURS_TIMEZONE

    async def get(self, conn: asyncpg.Connection, user_id: UUID) -> PreferencesOut:
        row = await self.repo.get(conn, user_id)
        return PreferencesOut.from_record(user_id, row, DEFAULT_CHANNELS, self._timezone(row))

    async def update(
        self, conn: asyncpg.Connection, user_id: UUID, payload: PreferencesUpdate
    ) -> PreferencesOut:
        existing = await self.repo.get(conn, user_id)
        channels = dict(DEFAULT_CHANNELS)
        if existing is not None:
            channels.update(existing["channels"])
        if payload.channels is not None:
            channels.update(payload.channels)

        quiet_start: time | None = None
        quiet_end: time | None = None
        if existing is not None:
            quiet_start = existing["quiet_hours_start"]
            quiet_end = existing["quiet_hours_end"]
        if payload.quiet_hours_start is not None and payload.quiet_hours_end is not None:
            quiet_start = parse_hhmm(payload.quiet_hours_start)
            quiet_end = parse_hhmm(payload.quiet_hours_end)

        locale = existing["locale"] if existing is not None else None
        if payload.locale is not None:
            locale = payload.locale

        row = await self.repo.upsert(
            conn,
            user_id=user_id,
            channels=channels,
            quiet_hours_start=quiet_start,
            quiet_hours_end=quiet_end,
            timezone=self._timezone(existing),
            locale=locale,
        )
        return PreferencesOut.from_record(user_id, row, DEFAULT_CHANNELS, self._timezone(row))

    @staticmethod
    def channel_enabled(preferences: PreferencesOut, channel: str) -> bool:
        return bool(preferences.channels.get(channel, False))
