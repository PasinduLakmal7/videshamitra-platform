"""Consumer idempotency."""

from __future__ import annotations

from uuid import UUID

import asyncpg


class DedupeRepository:
    async def try_insert(
        self,
        conn: asyncpg.Connection,
        *,
        consumer: str,
        event_id: UUID,
        event_type: str,
        notification_id: UUID,
    ) -> bool:
        row = await conn.fetchrow(
            """
            insert into notification.event_dedupe
                (consumer, event_id, event_type, notification_id)
            values ($1, $2, $3, $4)
            on conflict (consumer, event_id) do nothing
            returning event_id
            """,
            consumer,
            event_id,
            event_type,
            notification_id,
        )
        return row is not None
