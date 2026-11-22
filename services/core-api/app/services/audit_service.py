"""Audit trail service. Metadata must contain IDs, never PII or document text."""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

import asyncpg

from app.models.entities import CurrentUser, RequestInfo
from app.repositories.audit_repository import AuditRepository

logger = logging.getLogger(__name__)


class AuditService:
    def __init__(self, repo: AuditRepository | None = None) -> None:
        self.repo = repo or AuditRepository()

    async def record(
        self,
        conn: asyncpg.Connection,
        *,
        actor: CurrentUser | None,
        action: str,
        entity_type: str | None = None,
        entity_id: UUID | None = None,
        request: RequestInfo | None = None,
        metadata: dict[str, Any] | None = None,
        actor_service: str | None = None,
    ) -> None:
        actor_role = actor.role.value if actor else None
        data = dict(metadata or {})
        if actor_service:
            data["service"] = actor_service
        try:
            await self.repo.record(
                conn,
                actor_id=actor.id if actor else None,
                actor_role=actor_role,
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                ip_address=request.ip_address if request else None,
                user_agent=(request.user_agent[:500] if request and request.user_agent else None),
                metadata=data,
            )
        except asyncpg.DataError:
            # Invalid IP from a test client or proxy header: retry without it.
            await self.repo.record(
                conn,
                actor_id=actor.id if actor else None,
                actor_role=actor_role,
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                ip_address=None,
                user_agent=(request.user_agent[:500] if request and request.user_agent else None),
                metadata=data,
            )
        except Exception:
            # Auditing must never break the primary operation, but it must be loud.
            logger.exception("audit_write_failed", extra={"action": action})

    async def list_logs(
        self,
        conn: asyncpg.Connection,
        *,
        actor_id: UUID | None,
        action: str | None,
        entity_type: str | None,
        entity_id: UUID | None,
        page_size: int,
        offset: int,
    ):
        return await self.repo.list_logs(
            conn,
            actor_id=actor_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            page_size=page_size,
            offset=offset,
        )
