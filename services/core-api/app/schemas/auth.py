"""Auth DTOs."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.models.enums import LanguageCode, UserRole
from app.schemas.base import APIModel
from app.utils.text import normalize_phone


class RegisterRequest(BaseModel):
    email: str
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=1, max_length=200)
    phone: str | None = None
    preferred_language: LanguageCode = LanguageCode.EN
    country_of_work: str | None = None

    @field_validator("phone")
    @classmethod
    def _phone(cls, value: str | None) -> str | None:
        return normalize_phone(value)


class LoginRequest(BaseModel):
    email: str
    password: str = Field(min_length=1, max_length=128)


class OtpRequest(BaseModel):
    phone: str
    preferred_language: LanguageCode = LanguageCode.EN
    full_name: str | None = None

    @field_validator("phone")
    @classmethod
    def _phone(cls, value: str) -> str:
        normalized = normalize_phone(value)
        if not normalized:
            raise ValueError("A valid phone number is required")
        return normalized


class OtpVerifyRequest(BaseModel):
    phone: str
    token: str = Field(min_length=4, max_length=10)

    @field_validator("phone")
    @classmethod
    def _phone(cls, value: str) -> str:
        return normalize_phone(value) or value


class RefreshRequest(BaseModel):
    refresh_token: str


class SessionUser(APIModel):
    id: UUID
    email: str | None = None
    phone: str | None = None
    role: UserRole
    full_name: str | None = None
    preferred_language: LanguageCode
    country_of_work: str | None = None
    is_active: bool
    created_at: datetime | None = None


class SessionResponse(BaseModel):
    access_token: str
    refresh_token: str | None = None
    token_type: str = "bearer"
    expires_in: int | None = None
    user: SessionUser


class MeUpdate(BaseModel):
    full_name: str | None = Field(default=None, max_length=200)
    phone: str | None = None
    preferred_language: LanguageCode | None = None
    country_of_work: str | None = Field(default=None, max_length=100)

    @field_validator("phone")
    @classmethod
    def _phone(cls, value: str | None) -> str | None:
        return normalize_phone(value)


class MeOut(APIModel):
    id: UUID
    role: UserRole
    full_name: str | None = None
    phone: str | None = None
    preferred_language: LanguageCode
    country_of_work: str | None = None
    is_active: bool
    email: str | None = None
    created_at: datetime
    updated_at: datetime
