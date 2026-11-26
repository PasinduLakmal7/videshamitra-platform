"""Device registration business rules."""

from __future__ import annotations

import logging
from uuid import UUID

import asyncpg

from app.core.config import settings
from app.core.errors import NotFound
from app.repositories.device_repository import DeviceRepository

logger = logging.getLogger(__name__)


class DeviceService:
    def __init__(self, repo: DeviceRepository | None = None) -> None:
        self.repo = repo or DeviceRepository()

    async def register(
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
        async with conn.transaction():
            existing = await self.repo.get_by_token(conn, token)
            if existing is not None and existing["user_id"] != user_id:
                logger.info("device_token_reassigned")
            row = await self.repo.upsert(
                conn,
                user_id=user_id,
                token=token,
                platform=platform,
                app_version=app_version,
                device_id=device_id,
                locale=locale,
            )
            count = await self.repo.count_active(conn, user_id)
            while count > settings.MAX_DEVICES_PER_USER:
                evicted = await self.repo.deactivate_oldest(conn, user_id, exclude_id=row["id"])
                if evicted is None:
                    break
                logger.info("device_evicted_for_cap", extra={"device_id": str(evicted["id"])})
                count -= 1
        return row

    async def unregister(self, conn: asyncpg.Connection, *, user_id: UUID, token: str) -> None:
        existing = await self.repo.get_by_token(conn, token)
        if existing is None:
            return
        if existing["user_id"] != user_id:
            raise NotFound("Device not found")
        await self.repo.deactivate_by_id(conn, existing["id"])
