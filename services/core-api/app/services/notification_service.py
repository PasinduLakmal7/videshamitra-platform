"""In-app feed and notification request publishing.

`request_delivery` writes the feed row and the outbox event in the caller's
transaction, so one call yields exactly one feed item and one event.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

import asyncpg

from app.core.config import settings
from app.core.exceptions import NotFound
from app.events.envelope import enqueue_event
from app.events.schemas import NotificationRequestedData
from app.integrations.notification_client import NotificationClient
from app.models.enums import ConsentType, NotificationChannel, NotificationType
from app.repositories.notification_repository import NotificationRepository
from app.repositories.user_repository import UserRepository

logger = logging.getLogger(__name__)


class NotificationService:
    def __init__(
        self,
        repo: NotificationRepository | None = None,
        users: UserRepository | None = None,
        client: NotificationClient | None = None,
    ) -> None:
        self.repo = repo or NotificationRepository()
        self.users = users or UserRepository()
        self.client = client

    async def request_delivery(
        self,
        conn: asyncpg.Connection,
        *,
        user_id: UUID,
        notification_type: NotificationType | str,
        title: str,
        body: str,
        data: dict[str, Any] | None = None,
        deep_link: str | None = None,
        channels: list[str] | None = None,
    ) -> asyncpg.Record:
        type_value = (
            notification_type.value
            if isinstance(notification_type, NotificationType)
            else notification_type
        )
        notification = await self.repo.create(
            conn,
            user_id=user_id,
            notification_type=type_value,
            title=title,
            body=body,
            data=data or {},
            deep_link=deep_link,
        )

        user = await self.users.get_by_id(conn, user_id)
        locale = user["preferred_language"] if user else "en"
        requested = channels or [NotificationChannel.PUSH.value]
        allowed = set(requested)

        if NotificationChannel.WHATSAPP.value in allowed:
            consent = await self.users.latest_consent(conn, user_id, ConsentType.WHATSAPP)
            if not consent or not consent["granted"]:
                allowed.discard(NotificationChannel.WHATSAPP.value)

        payload = NotificationRequestedData(
            notification_id=notification["id"],
            user_id=user_id,
            locale=str(locale),
            type=type_value,
            title=title,
            body=body,
            data=data or {},
            deep_link=deep_link,
            channels=sorted(allowed),
        )
        await enqueue_event(
            conn,
            event_type="notification.requested",
            data=payload.model_dump(mode="json"),
            stream=settings.NOTIFICATION_REQUESTS_STREAM,
        )
        return notification

    async def create_in_app(
        self,
        conn: asyncpg.Connection,
        *,
        user_id: UUID,
        notification_type: NotificationType | str,
        title: str,
        body: str,
        data: dict[str, Any] | None = None,
        deep_link: str | None = None,
    ) -> asyncpg.Record:
        type_value = (
            notification_type.value
            if isinstance(notification_type, NotificationType)
            else notification_type
        )
        return await self.repo.create(
            conn,
            user_id=user_id,
            notification_type=type_value,
            title=title,
            body=body,
            data=data or {},
            deep_link=deep_link,
        )

    async def notify_staff(
        self,
        conn: asyncpg.Connection,
        *,
        title: str,
        body: str,
        data: dict[str, Any] | None = None,
        deep_link: str | None = None,
    ) -> int:
        staff = await self.repo.staff_ids(conn)
        for user_id in staff:
            await self.repo.create(
                conn,
                user_id=user_id,
                notification_type=NotificationType.SYSTEM.value,
                title=title,
                body=body,
                data=data or {},
                deep_link=deep_link,
            )
        return len(staff)

    async def list_feed(
        self,
        conn: asyncpg.Connection,
        *,
        user_id: UUID,
        notification_type: str | None,
        unread_only: bool,
        page_size: int,
        offset: int,
        order_by: str,
    ):
        return await self.repo.list_notifications(
            conn,
            user_id=user_id,
            notification_type=notification_type,
            unread_only=unread_only,
            page_size=page_size,
            offset=offset,
            order_by=order_by,
        )

    async def unread_count(self, conn: asyncpg.Connection, user_id: UUID) -> int:
        return await self.repo.unread_count(conn, user_id)

    async def mark_read(
        self, conn: asyncpg.Connection, *, user_id: UUID, notification_id: UUID
    ) -> asyncpg.Record:
        row = await self.repo.mark_read(conn, notification_id, user_id)
        if row is None:
            raise NotFound("Notification not found")
        return row

    async def mark_all_read(self, conn: asyncpg.Connection, user_id: UUID) -> int:
        return await self.repo.mark_all_read(conn, user_id)

    # --- notification-service proxy -------------------------------------
    def _client(self) -> NotificationClient:
        if self.client is None:
            self.client = NotificationClient(settings.NOTIFICATION_SERVICE_URL)
        return self.client

    async def register_device(self, user_id: UUID, payload: dict[str, Any]) -> dict[str, Any]:
        body = {**payload, "user_id": str(user_id)}
        return await self._client().register_device(body)

    async def unregister_device(self, user_id: UUID, token: str) -> dict[str, Any]:
        return await self._client().unregister_device(token, str(user_id))

    async def get_preferences(self, user_id: UUID) -> dict[str, Any]:
        return await self._client().get_preferences(str(user_id))

    async def update_preferences(self, user_id: UUID, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._client().update_preferences(str(user_id), payload)
