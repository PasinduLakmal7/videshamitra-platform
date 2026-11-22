"""User profiles, consent history and admin role/status changes."""

from __future__ import annotations

import ipaddress
from uuid import UUID

import asyncpg

from app.core.exceptions import Conflict, Forbidden, NotFound
from app.core.permissions import is_admin, is_staff
from app.models.entities import CurrentUser, RequestInfo
from app.models.enums import UserRole
from app.repositories.user_repository import UserRepository
from app.schemas.user import ConsentCreate, UserUpdate
from app.services.audit_service import AuditService


def _valid_ip(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return str(ipaddress.ip_address(value))
    except ValueError:
        return None


class UserService:
    def __init__(
        self,
        repo: UserRepository | None = None,
        audit: AuditService | None = None,
    ) -> None:
        self.repo = repo or UserRepository()
        self.audit = audit or AuditService()

    async def list_users(
        self,
        conn: asyncpg.Connection,
        *,
        actor: CurrentUser,
        page: int,
        page_size: int,
        offset: int,
        order_by: str,
        role: str | None,
        q: str | None,
        is_active: bool | None,
    ):
        if not is_staff(actor):
            raise Forbidden("Staff access required")
        return await self.repo.list_users(
            conn,
            page=page,
            page_size=page_size,
            offset=offset,
            order_by=order_by,
            role=role,
            q=q,
            is_active=is_active,
        )

    async def get_user(
        self, conn: asyncpg.Connection, *, actor: CurrentUser, user_id: UUID
    ) -> asyncpg.Record:
        if actor.id != user_id and not is_staff(actor):
            raise Forbidden("You do not have access to this profile")
        row = await self.repo.get_by_id(conn, user_id)
        if row is None:
            raise NotFound("User not found")
        return row

    async def update_user(
        self,
        conn: asyncpg.Connection,
        *,
        actor: CurrentUser,
        user_id: UUID,
        payload: UserUpdate,
        request: RequestInfo,
    ) -> asyncpg.Record:
        if actor.id != user_id and not is_staff(actor):
            raise Forbidden("You cannot update another user's profile")
        fields = payload.model_dump(exclude_unset=True, exclude_none=True)
        row = await self.repo.update_profile(conn, user_id, fields)
        if row is None:
            raise NotFound("User not found")
        await self.audit.record(
            conn,
            actor=actor,
            action="user.profile_updated",
            entity_type="user",
            entity_id=user_id,
            request=request,
            metadata={"fields": sorted(fields)},
        )
        return row

    async def update_role(
        self,
        conn: asyncpg.Connection,
        *,
        actor: CurrentUser,
        user_id: UUID,
        role: UserRole,
        request: RequestInfo,
    ) -> asyncpg.Record:
        if not is_admin(actor):
            raise Forbidden("Admin access required")
        row = await self.repo.set_role(conn, user_id, role)
        if row is None:
            raise NotFound("User not found")
        await self.audit.record(
            conn,
            actor=actor,
            action="user.role_changed",
            entity_type="user",
            entity_id=user_id,
            request=request,
            metadata={"role": role.value},
        )
        return row

    async def update_status(
        self,
        conn: asyncpg.Connection,
        *,
        actor: CurrentUser,
        user_id: UUID,
        is_active: bool,
        request: RequestInfo,
    ) -> asyncpg.Record:
        if not is_admin(actor):
            raise Forbidden("Admin access required")
        if actor.id == user_id and not is_active:
            raise Conflict("You cannot deactivate your own account", code="self_deactivation")
        row = await self.repo.set_active(conn, user_id, is_active)
        if row is None:
            raise NotFound("User not found")
        await self.audit.record(
            conn,
            actor=actor,
            action="user.status_changed",
            entity_type="user",
            entity_id=user_id,
            request=request,
            metadata={"is_active": is_active},
        )
        return row

    async def list_consents(
        self, conn: asyncpg.Connection, *, actor: CurrentUser
    ) -> list[asyncpg.Record]:
        return await self.repo.list_consents(conn, actor.id)

    async def create_consent(
        self,
        conn: asyncpg.Connection,
        *,
        actor: CurrentUser,
        payload: ConsentCreate,
        request: RequestInfo,
    ) -> asyncpg.Record:
        row = await self.repo.create_consent(
            conn,
            user_id=actor.id,
            consent_type=payload.type,
            granted=payload.granted,
            version=payload.version,
            ip_address=_valid_ip(request.ip_address),
            user_agent=(request.user_agent[:500] if request.user_agent else None),
        )
        await self.audit.record(
            conn,
            actor=actor,
            action="consent.updated",
            entity_type="user_consent",
            entity_id=row["id"],
            request=request,
            metadata={"type": payload.type.value, "granted": payload.granted},
        )
        return row
