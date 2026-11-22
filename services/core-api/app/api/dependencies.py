"""FastAPI dependencies: auth, roles, DB, clients and request metadata."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID

import asyncpg
from fastapi import Depends, Header, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.exceptions import Forbidden, Unauthorized
from app.core.request_id import user_id_var
from app.core.security import verify_supabase_token
from app.db.pool import get_connection
from app.models.entities import CurrentUser, RequestInfo
from app.models.enums import UserRole
from app.repositories.user_repository import UserRepository

bearer_scheme = HTTPBearer(auto_error=False)
_user_repo = UserRepository()


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    conn: asyncpg.Connection = Depends(get_connection),
) -> CurrentUser:
    if credentials is None or not credentials.credentials:
        raise Unauthorized("Missing bearer token", code="token_missing")
    claims = await verify_supabase_token(credentials.credentials)
    try:
        user_id = UUID(str(claims["sub"]))
    except (KeyError, ValueError) as exc:
        raise Unauthorized("Token subject is invalid", code="invalid_token") from exc

    row = await _user_repo.get_by_id(conn, user_id)
    if row is None:
        try:
            row = await _user_repo.ensure_from_claims(conn, user_id, claims)
        except Exception as exc:
            raise Unauthorized(
                "No profile exists for this identity", code="profile_missing"
            ) from exc
    if not row["is_active"]:
        raise Forbidden("Account is inactive", code="account_inactive")

    user = CurrentUser.from_record(row)
    request.state.user = user
    request.state.claims = claims
    user_id_var.set(str(user.id))
    return user


def require_roles(*roles: UserRole):
    async def dependency(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if user.role not in roles:
            raise Forbidden("Your role cannot access this resource")
        return user

    return dependency


staff_user = require_roles(UserRole.CASEWORKER, UserRole.ADMIN)
admin_user = require_roles(UserRole.ADMIN)


def get_request_info(request: Request) -> RequestInfo:
    return RequestInfo.from_request(request)


def get_idempotency_key(
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> str | None:
    return idempotency_key


def get_ai_client(request: Request):
    return request.app.state.ai_client


def get_notification_client(request: Request):
    return request.app.state.notification_client


def get_storage(request: Request):
    return request.app.state.storage


def get_supabase_auth(request: Request):
    return request.app.state.supabase_auth


def get_ai_service_client(request: Request):
    return request.app.state.ai_client


async def get_connection_optional() -> AsyncIterator[asyncpg.Connection | None]:
    try:
        async with request_scope_connection() as conn:  # pragma: no cover
            yield conn
    except Exception:
        yield None


def request_scope_connection():  # pragma: no cover - testing helper
    from app.db.pool import acquire

    return acquire()


def get_pool_state(request: Request) -> dict[str, Any]:
    return {
        "db": getattr(request.app.state, "pool", None) is not None,
        "redis": getattr(request.app.state, "redis", None) is not None,
    }
