"""User and consent DTOs."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import ConsentType, LanguageCode, UserRole
from app.schemas.auth import MeUpdate
from app.schemas.base import APIModel


class UserOut(APIModel):
    id: UUID
    role: UserRole
    full_name: str | None = None
    phone: str | None = None
    preferred_language: LanguageCode
    country_of_work: str | None = None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class UserUpdate(MeUpdate):
    """Staff/self profile update (role/status are separate admin endpoints)."""


class RoleUpdate(BaseModel):
    role: UserRole


class StatusUpdate(BaseModel):
    is_active: bool


class ConsentCreate(BaseModel):
    type: ConsentType
    granted: bool
    version: str = Field(default="1", max_length=32)


class ConsentOut(APIModel):
    id: UUID
    user_id: UUID
    type: ConsentType
    granted: bool
    version: str
    granted_at: datetime | None = None
    revoked_at: datetime | None = None
    ip_address: str | None = None
    user_agent: str | None = None
    created_at: datetime
