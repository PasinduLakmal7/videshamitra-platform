"""Small immutable domain objects used across layers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from app.models.enums import LanguageCode, UserRole


@dataclass(frozen=True, slots=True)
class CurrentUser:
    id: UUID
    role: UserRole
    full_name: str | None = None
    phone: str | None = None
    preferred_language: LanguageCode = LanguageCode.EN
    country_of_work: str | None = None
    is_active: bool = True

    @property
    def is_staff(self) -> bool:
        return self.role in (UserRole.CASEWORKER, UserRole.ADMIN)

    @property
    def is_admin(self) -> bool:
        return self.role == UserRole.ADMIN

    @classmethod
    def from_record(cls, row: Any) -> CurrentUser:
        return cls(
            id=row["id"],
            role=UserRole(row["role"]),
            full_name=row["full_name"],
            phone=row["phone"],
            preferred_language=LanguageCode(row["preferred_language"]),
            country_of_work=row["country_of_work"],
            is_active=bool(row["is_active"]),
        )


@dataclass(frozen=True, slots=True)
class ServiceIdentity:
    service: str
    claims: dict[str, Any]


@dataclass(frozen=True, slots=True)
class RequestInfo:
    ip_address: str | None
    user_agent: str | None

    @classmethod
    def from_request(cls, request: Any) -> RequestInfo:
        forwarded = request.headers.get("X-Forwarded-For", "")
        ip = forwarded.split(",")[0].strip() if forwarded else None
        if not ip and request.client:
            ip = request.client.host
        return cls(ip_address=ip, user_agent=request.headers.get("User-Agent"))
