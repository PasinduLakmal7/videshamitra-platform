"""Device-token persistence."""

from __future__ import annotations

from uuid import UUID

import asyncpg


class DeviceRepository:
    async def get_by_token(self, conn: asyncpg.Connection, token: str):
        return await conn.fetchrow(
            "select * from notification.device_tokens where token = $1", token
        )

    async def get_by_id(self, conn: asyncpg.Connection, device_id):
        return await conn.fetchrow(
            "select * from notification.device_tokens where id = $1", device_id
        )

    async def list_active(self, conn: asyncpg.Connection, user_id: UUID):
        return await conn.fetch(
            """
            select * from notification.device_tokens
            where user_id = $1 and is_active
            order by last_seen_at desc
            """,
            user_id,
        )

    async def count_active(self, conn: asyncpg.Connection, user_id: UUID) -> int:
        return await conn.fetchval(
            "select count(*) from notification.device_tokens where user_id = $1 and is_active",
            user_id,
        )

    async def deactivate_oldest(
        self, conn: asyncpg.Connection, user_id: UUID, *, exclude_id: UUID | None = None
    ):
        return await conn.fetchrow(
            """
            update notification.device_tokens
            set is_active = false
            where id = (
                select id from notification.device_tokens
                where user_id = $1 and is_active
                  and ($2::uuid is null or id <> $2::uuid)
                order by last_seen_at asc, created_at asc
                limit 1
            )
            returning *
            """,
            user_id,
            exclude_id,
        )

    async def upsert(
        self,
        conn: asyncpg.Connection,
        *,
        user_id: UUID,
        token: str,
        platform: str,
        app_version: str | None,
        device_id: str | None,
        locale: str | None,
    ):
        return await conn.fetchrow(
            """
            insert into notification.device_tokens
                (user_id, token, platform, app_version, device_id, locale)
            values ($1, $2, $3, $4, $5, $6)
            on conflict (token) do update set
                user_id = excluded.user_id,
                platform = excluded.platform,
                app_version = excluded.app_version,
                device_id = excluded.device_id,
                locale = excluded.locale,
                is_active = true,
                last_seen_at = now(),
                updated_at = now()
            returning *
            """,
            user_id,
            token,
            platform,
            app_version,
            device_id,
            locale,
        )

    async def deactivate_by_id(self, conn: asyncpg.Connection, device_id: UUID):
        return await conn.fetchrow(
            """
            update notification.device_tokens
            set is_active = false
            where id = $1
            returning *
            """,
            device_id,
        )

    async def deactivate_by_token(self, conn: asyncpg.Connection, token: str):
        return await conn.fetchrow(
            """
            update notification.device_tokens
            set is_active = false
            where token = $1
            returning *
            """,
            token,
        )
