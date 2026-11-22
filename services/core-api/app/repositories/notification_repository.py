"""SQL for the in-app notification feed."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import asyncpg

SORT_COLUMNS = {"created_at": "created_at", "type": "type"}


class NotificationRepository:
    async def create(
        self,
        conn: asyncpg.Connection,
        *,
        user_id: UUID,
        notification_type: str,
        title: str,
        body: str,
        data: dict[str, Any],
        deep_link: str | None,
    ) -> asyncpg.Record:
        return await conn.fetchrow(
            """
            insert into core.notifications (user_id, type, title, body, data, deep_link)
            values ($1, $2::core.notification_type, $3, $4, $5, $6)
            returning *
            """,
            user_id,
            notification_type,
            title[:200],
            body[:4000],
            data,
            deep_link,
        )

    async def get(self, conn: asyncpg.Connection, notification_id: UUID) -> asyncpg.Record | None:
        return await conn.fetchrow(
            "select * from core.notifications where id = $1", notification_id
        )

    async def list_notifications(
        self,
        conn: asyncpg.Connection,
        *,
        user_id: UUID,
        notification_type: str | None,
        unread_only: bool,
        page_size: int,
        offset: int,
        order_by: str,
    ) -> tuple[list[asyncpg.Record], int]:
        where = """
            where user_id = $1
              and ($2::text is null or type::text = $2)
              and (not $3::boolean or read_at is null)
        """
        params = [user_id, notification_type, unread_only]
        total = await conn.fetchval(f"select count(*) from core.notifications {where}", *params)
        rows = await conn.fetch(
            f"""
            select * from core.notifications
            {where}
            order by {order_by}
            limit $4 offset $5
            """,
            *params,
            page_size,
            offset,
        )
        return list(rows), int(total or 0)

    async def unread_count(self, conn: asyncpg.Connection, user_id: UUID) -> int:
        return int(
            await conn.fetchval(
                "select count(*) from core.notifications where user_id = $1 and read_at is null",
                user_id,
            )
            or 0
        )

    async def mark_read(
        self, conn: asyncpg.Connection, notification_id: UUID, user_id: UUID
    ) -> asyncpg.Record | None:
        return await conn.fetchrow(
            """
            update core.notifications
            set read_at = coalesce(read_at, now())
            where id = $1 and user_id = $2
            returning *
            """,
            notification_id,
            user_id,
        )

    async def mark_all_read(self, conn: asyncpg.Connection, user_id: UUID) -> int:
        result = await conn.execute(
            """
            update core.notifications
            set read_at = now()
            where user_id = $1 and read_at is null
            """,
            user_id,
        )
        try:
            return int(result.split()[-1])
        except (ValueError, IndexError):
            return 0

    async def staff_ids(self, conn: asyncpg.Connection) -> list[UUID]:
        rows = await conn.fetch(
            "select id from core.users where role in ('caseworker', 'admin') and is_active"
        )
        return [row["id"] for row in rows]
