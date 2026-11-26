"""Preference persistence."""

from __future__ import annotations

from datetime import time
from uuid import UUID

import asyncpg


class PreferenceRepository:
    async def get(self, conn: asyncpg.Connection, user_id: UUID):
        return await conn.fetchrow(
            "select * from notification.notification_preferences where user_id = $1",
            user_id,
        )

    async def upsert(
        self,
        conn: asyncpg.Connection,
        *,
        user_id: UUID,
        channels: dict[str, bool],
        quiet_hours_start: time | None,
        quiet_hours_end: time | None,
        timezone: str,
        locale: str | None,
    ):
        return await conn.fetchrow(
            """
            insert into notification.notification_preferences
                (user_id, channels, quiet_hours_start, quiet_hours_end, timezone, locale)
            values ($1, $2, $3, $4, $5, $6)
            on conflict (user_id) do update set
                channels = excluded.channels,
                quiet_hours_start = excluded.quiet_hours_start,
                quiet_hours_end = excluded.quiet_hours_end,
                timezone = excluded.timezone,
                locale = excluded.locale,
                updated_at = now()
            returning *
            """,
            user_id,
            channels,
            quiet_hours_start,
            quiet_hours_end,
            timezone,
            locale,
        )
