"""Supabase Auth proxy plus core profile bootstrap."""

from __future__ import annotations

import hashlib
import hmac
import logging
from typing import Any
from uuid import UUID

import asyncpg

from app.core.config import settings
from app.core.exceptions import Conflict, RateLimited, ServiceUnavailable, Unauthorized
from app.core.security import create_dev_token
from app.db import redis as redis_db
from app.integrations.supabase.auth import SupabaseAuthClient
from app.models.entities import CurrentUser, RequestInfo
from app.repositories.user_repository import UserRepository
from app.schemas.auth import (
    LoginRequest,
    MeOut,
    OtpRequest,
    OtpVerifyRequest,
    RefreshRequest,
    RegisterRequest,
    SessionResponse,
    SessionUser,
)
from app.services.audit_service import AuditService
from app.services.user_service import UserService

logger = logging.getLogger(__name__)


class AuthService:
    def __init__(
        self,
        client: SupabaseAuthClient | None = None,
        users: UserRepository | None = None,
        audit: AuditService | None = None,
    ) -> None:
        self.client = client or SupabaseAuthClient()
        self.users = users or UserRepository()
        self.audit = audit or AuditService()
        self.user_service = UserService(self.users, self.audit)

    async def _rate_limit(
        self,
        *,
        scope: str,
        ip: str | None,
        subject: str | None,
        limit: int,
        fail_closed: bool = True,
    ) -> None:
        subject_key = hashlib.sha256((subject or "unknown").encode()).hexdigest()[:32]
        keys = [f"{scope}:ip:{ip or 'unknown'}", f"{scope}:subject:{subject_key}"]
        try:
            client = redis_db.get_client()
            pipe = client.pipeline()
            for key in keys:
                pipe.incr(key)
                pipe.expire(key, 600)
            counts = await pipe.execute()
        except Exception as exc:
            logger.warning("auth_rate_limit_unavailable", extra={"scope": scope})
            if fail_closed:
                raise ServiceUnavailable(
                    "Sign-in is temporarily unavailable", code="rate_limit_unavailable"
                ) from exc
            return
        if any(int(count) > limit for count in counts[::2]):
            raise RateLimited("Too many attempts; try again later")

    async def _profile(self, conn: asyncpg.Connection, auth_user: dict[str, Any]) -> asyncpg.Record:
        user_id = UUID(str(auth_user["id"]))
        row = await self.users.get_by_id(conn, user_id)
        if row is None:
            claims = {
                "sub": str(user_id),
                "phone": auth_user.get("phone"),
                "user_metadata": auth_user.get("user_metadata") or {},
            }
            row = await self.users.ensure_from_claims(conn, user_id, claims)
        return row

    def _session(
        self, session: dict[str, Any], profile: asyncpg.Record, auth_user: dict[str, Any]
    ) -> SessionResponse:
        if not session.get("access_token"):
            raise Conflict(
                "Email confirmation is required before signing in",
                code="email_confirmation_required",
            )
        return SessionResponse(
            access_token=session["access_token"],
            refresh_token=session.get("refresh_token"),
            token_type=session.get("token_type", "bearer"),
            expires_in=session.get("expires_in"),
            user=SessionUser(
                id=profile["id"],
                email=auth_user.get("email"),
                phone=profile["phone"] or auth_user.get("phone"),
                role=profile["role"],
                full_name=profile["full_name"],
                preferred_language=profile["preferred_language"],
                country_of_work=profile["country_of_work"],
                is_active=profile["is_active"],
                created_at=profile["created_at"],
            ),
        )

    async def register(
        self,
        conn: asyncpg.Connection,
        *,
        payload: RegisterRequest,
        request: RequestInfo,
    ) -> SessionResponse:
        session = await self.client.sign_up(
            email=payload.email,
            password=payload.password,
            data={
                "full_name": payload.full_name,
                "phone": payload.phone,
                "preferred_language": payload.preferred_language.value,
                "country_of_work": payload.country_of_work,
            },
        )
        auth_user = session.get("user") or {}
        if not auth_user.get("id"):
            raise Unauthorized("Registration failed", code="registration_failed")
        profile = await self._profile(conn, auth_user)
        # Self-registration can only ever be a worker.
        if profile["role"] != "worker":
            await self.users.set_role(conn, profile["id"], "worker")
            profile = await self.users.get_by_id(conn, profile["id"])  # type: ignore[assignment]
        await self.audit.record(
            conn,
            actor=CurrentUser.from_record(profile),
            action="auth.registered",
            entity_type="user",
            entity_id=profile["id"],
            request=request,
        )
        return self._session(session, profile, auth_user)

    async def login(
        self,
        conn: asyncpg.Connection,
        *,
        payload: LoginRequest,
        request: RequestInfo,
    ) -> SessionResponse:
        await self._rate_limit(
            scope="login",
            ip=request.ip_address,
            subject=payload.email.lower(),
            limit=settings.LOGIN_RATE_LIMIT_PER_10_MIN,
            fail_closed=False,
        )
        session = await self.client.password_login(email=payload.email, password=payload.password)
        auth_user = session.get("user") or {}
        profile = await self._profile(conn, auth_user)
        if not profile["is_active"]:
            raise Unauthorized("Account is inactive", code="account_inactive")
        await self.audit.record(
            conn,
            actor=CurrentUser.from_record(profile),
            action="auth.login",
            entity_type="user",
            entity_id=profile["id"],
            request=request,
        )
        return self._session(session, profile, auth_user)

    async def request_otp(
        self,
        conn: asyncpg.Connection,
        *,
        payload: OtpRequest,
        request: RequestInfo,
    ) -> dict[str, Any]:
        await self._rate_limit(
            scope="otp",
            ip=request.ip_address,
            subject=payload.phone,
            limit=settings.OTP_RATE_LIMIT_PER_10_MIN,
        )
        data = {
            "full_name": payload.full_name,
            "preferred_language": payload.preferred_language.value,
        }
        await self.client.request_otp(phone=payload.phone, data=data)
        return {"message": "OTP sent"}

    async def verify_otp(
        self,
        conn: asyncpg.Connection,
        *,
        payload: OtpVerifyRequest,
        request: RequestInfo,
    ) -> SessionResponse:
        await self._rate_limit(
            scope="otp_verify",
            ip=request.ip_address,
            subject=payload.phone,
            limit=settings.OTP_RATE_LIMIT_PER_10_MIN,
        )
        if (
            settings.AUTH_DEV_OTP
            and settings.is_dev
            and hmac.compare_digest(payload.token, settings.AUTH_DEV_OTP)
        ):
            if not settings.supabase_admin_configured:
                raise ServiceUnavailable(
                    "Dev OTP needs Supabase admin credentials",
                    code="auth_admin_not_configured",
                )
            profile = await self.users.get_by_phone(conn, payload.phone)
            if profile is None:
                try:
                    created = await self.client.admin_create_user(
                        phone=payload.phone,
                        phone_confirm=True,
                        user_metadata={"phone": payload.phone},
                    )
                except Conflict:
                    created = None
                if created and created.get("id"):
                    profile = await self._profile(conn, created)
            if profile is None:
                raise Unauthorized("No account for this phone", code="user_not_found")
            if profile["role"] != "worker" or not profile["is_active"]:
                raise Unauthorized(
                    "Dev OTP is limited to active worker accounts", code="dev_otp_forbidden"
                )
            await self.audit.record(
                conn,
                actor=CurrentUser.from_record(profile),
                action="auth.dev_otp_login",
                entity_type="user",
                entity_id=profile["id"],
                request=request,
            )
            token = create_dev_token(str(profile["id"]))
            return SessionResponse(
                access_token=token,
                refresh_token=None,
                token_type="bearer",
                expires_in=3600,
                user=SessionUser(
                    id=profile["id"],
                    email=None,
                    phone=profile["phone"],
                    role=profile["role"],
                    full_name=profile["full_name"],
                    preferred_language=profile["preferred_language"],
                    country_of_work=profile["country_of_work"],
                    is_active=profile["is_active"],
                    created_at=profile["created_at"],
                ),
            )

        session = await self.client.verify_otp(phone=payload.phone, token=payload.token)
        auth_user = session.get("user") or {}
        profile = await self._profile(conn, auth_user)
        if not profile["is_active"]:
            raise Unauthorized("Account is inactive", code="account_inactive")
        await self.audit.record(
            conn,
            actor=CurrentUser.from_record(profile),
            action="auth.otp_verified",
            entity_type="user",
            entity_id=profile["id"],
            request=request,
        )
        return self._session(session, profile, auth_user)

    async def refresh(self, *, payload: RefreshRequest) -> SessionResponse:
        session = await self.client.refresh(refresh_token=payload.refresh_token)
        auth_user = session.get("user") or {}
        # refresh can be called without a DB connection; profile lives in core.
        from app.db.pool import acquire

        async with acquire() as conn:
            profile = await self._profile(conn, auth_user)
        if not profile["is_active"]:
            raise Unauthorized("Account is inactive", code="account_inactive")
        return self._session(session, profile, auth_user)

    async def logout(self, access_token: str) -> None:
        await self.client.logout(access_token)

    async def me(
        self,
        conn: asyncpg.Connection,
        *,
        actor: CurrentUser,
        email: str | None = None,
    ) -> MeOut:
        row = await self.users.get_by_id(conn, actor.id)
        if row is None:
            raise Unauthorized("Profile not found", code="profile_missing")
        return MeOut.from_record({**dict(row), "email": email})
