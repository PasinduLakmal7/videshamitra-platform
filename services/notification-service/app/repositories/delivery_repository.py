"""Delivery and attempt persistence."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

import asyncpg


class DeliveryRepository:
    async def create(
        self,
        conn: asyncpg.Connection,
        *,
        notification_id: UUID,
        user_id: UUID,
        notification_type: str,
        locale: str,
        title: str,
        body: str,
        deep_link: str | None,
        payload: dict[str, Any],
        channel: str,
        device_token_id: UUID | None,
        status: str,
        pending_reason: str | None,
        next_attempt_at: datetime,
        last_error_code: str | None = None,
    ):
        return await conn.fetchrow(
            """
            insert into notification.deliveries
                (notification_id, user_id, notification_type, locale, title, body,
                 deep_link, payload, channel, device_token_id, status, pending_reason,
                 next_attempt_at, last_error_code)
            values ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
            on conflict do nothing
            returning *
            """,
            notification_id,
            user_id,
            notification_type,
            locale,
            title,
            body,
            deep_link,
            payload,
            channel,
            device_token_id,
            status,
            pending_reason,
            next_attempt_at,
            last_error_code,
        )

    async def get(self, conn: asyncpg.Connection, delivery_id: UUID):
        return await conn.fetchrow(
            "select * from notification.deliveries where id = $1", delivery_id
        )

    async def list_for_notification(self, conn: asyncpg.Connection, notification_id: UUID):
        return await conn.fetch(
            """
            select * from notification.deliveries
            where notification_id = $1
            order by channel, created_at
            """,
            notification_id,
        )

    async def claim_due(self, conn: asyncpg.Connection, limit: int):
        return await conn.fetch(
            """
            update notification.deliveries
            set status = 'sending', updated_at = now()
            where id in (
                select id from notification.deliveries
                where status = 'pending' and next_attempt_at <= now()
                order by next_attempt_at
                for update skip locked
                limit $1
            )
            returning *
            """,
            limit,
        )

    async def reset_stale_sending(self, conn: asyncpg.Connection, timeout_seconds: int) -> int:
        rows = await conn.fetch(
            """
            update notification.deliveries
            set status = 'pending',
                pending_reason = 'retry',
                next_attempt_at = now(),
                last_error_code = coalesce(last_error_code, 'stale_sending')
            where status = 'sending'
              and updated_at < now() - make_interval(secs => $1)
            returning id
            """,
            timeout_seconds,
        )
        return len(rows)

    async def record_attempt(
        self,
        conn: asyncpg.Connection,
        *,
        delivery_id: UUID,
        attempt_number: int,
        provider: str,
        status: str,
        http_status: int | None = None,
        provider_message_id: str | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> None:
        await conn.execute(
            """
            insert into notification.delivery_attempts
                (delivery_id, attempt_number, provider, status, http_status,
                 provider_message_id, error_code, error_message)
            values ($1, $2, $3, $4, $5, $6, $7, $8)
            on conflict (delivery_id, attempt_number) do nothing
            """,
            delivery_id,
            attempt_number,
            provider,
            status,
            http_status,
            provider_message_id,
            error_code,
            (error_message or "")[:1000] or None,
        )

    async def mark_sent(
        self,
        conn: asyncpg.Connection,
        *,
        delivery_id: UUID,
        attempt_count: int,
        provider_message_id: str | None,
    ):
        return await conn.fetchrow(
            """
            update notification.deliveries
            set status = 'sent',
                attempt_count = $2,
                provider_message_id = $3,
                last_error_code = null,
                last_error = null,
                sent_at = now(),
                updated_at = now()
            where id = $1
            returning *
            """,
            delivery_id,
            attempt_count,
            provider_message_id,
        )

    async def mark_retry(
        self,
        conn: asyncpg.Connection,
        *,
        delivery_id: UUID,
        attempt_count: int,
        next_attempt_at: datetime,
        error_code: str | None,
        error_message: str | None,
    ):
        return await conn.fetchrow(
            """
            update notification.deliveries
            set status = 'pending',
                pending_reason = 'retry',
                attempt_count = $2,
                next_attempt_at = $3,
                last_error_code = $4,
                last_error = $5,
                updated_at = now()
            where id = $1
            returning *
            """,
            delivery_id,
            attempt_count,
            next_attempt_at,
            error_code,
            (error_message or "")[:1000] or None,
        )

    async def mark_failed(
        self,
        conn: asyncpg.Connection,
        *,
        delivery_id: UUID,
        attempt_count: int,
        error_code: str | None,
        error_message: str | None,
    ):
        return await conn.fetchrow(
            """
            update notification.deliveries
            set status = 'failed',
                pending_reason = null,
                attempt_count = $2,
                last_error_code = $3,
                last_error = $4,
                updated_at = now()
            where id = $1
            returning *
            """,
            delivery_id,
            attempt_count,
            error_code,
            (error_message or "")[:1000] or None,
        )
