"""Authentication endpoints (thin Supabase Auth proxy)."""

from __future__ import annotations

from typing import Any

import asyncpg
from fastapi import APIRouter, Depends, Request, status
from fastapi.security import HTTPAuthorizationCredentials

from app.api.dependencies import (
    bearer_scheme,
    get_current_user,
    get_request_info,
    get_supabase_auth,
)
from app.db.pool import get_connection
from app.models.entities import CurrentUser, RequestInfo
from app.schemas.auth import (
    LoginRequest,
    MeOut,
    MeUpdate,
    OtpRequest,
    OtpVerifyRequest,
    RefreshRequest,
    RegisterRequest,
    SessionResponse,
)
from app.schemas.common import ApiResponse, MessageData
from app.schemas.user import UserOut
from app.services.auth_service import AuthService
from app.services.user_service import UserService

router = APIRouter()


def _service(auth_client) -> AuthService:  # type: ignore[no-untyped-def]
    return AuthService(client=auth_client)


@router.post(
    "/register",
    response_model=ApiResponse[SessionResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Worker self-registration",
)
async def register(
    payload: RegisterRequest,
    request: Request,
    conn: asyncpg.Connection = Depends(get_connection),
    request_info: RequestInfo = Depends(get_request_info),
    auth_client=Depends(get_supabase_auth),
):
    from app.schemas.common import ok

    service = _service(auth_client)
    session = await service.register(conn, payload=payload, request=request_info)
    return ok(session.model_dump(mode="json"))


@router.post("/login", response_model=ApiResponse[SessionResponse], summary="Staff email login")
async def login(
    payload: LoginRequest,
    request: Request,
    conn: asyncpg.Connection = Depends(get_connection),
    request_info: RequestInfo = Depends(get_request_info),
    auth_client=Depends(get_supabase_auth),
):
    from app.schemas.common import ok

    service = _service(auth_client)
    session = await service.login(conn, payload=payload, request=request_info)
    return ok(session.model_dump(mode="json"))


@router.post(
    "/otp/request", response_model=ApiResponse[dict[str, Any]], summary="Request a worker phone OTP"
)
async def request_otp(
    payload: OtpRequest,
    request: Request,
    conn: asyncpg.Connection = Depends(get_connection),
    request_info: RequestInfo = Depends(get_request_info),
    auth_client=Depends(get_supabase_auth),
):
    from app.schemas.common import ok

    service = _service(auth_client)
    result = await service.request_otp(conn, payload=payload, request=request_info)
    return ok(result)


@router.post(
    "/otp/verify", response_model=ApiResponse[SessionResponse], summary="Verify a worker phone OTP"
)
async def verify_otp(
    payload: OtpVerifyRequest,
    request: Request,
    conn: asyncpg.Connection = Depends(get_connection),
    request_info: RequestInfo = Depends(get_request_info),
    auth_client=Depends(get_supabase_auth),
):
    from app.schemas.common import ok

    service = _service(auth_client)
    session = await service.verify_otp(conn, payload=payload, request=request_info)
    return ok(session.model_dump(mode="json"))


@router.post("/refresh", response_model=ApiResponse[SessionResponse], summary="Refresh a session")
async def refresh(
    payload: RefreshRequest,
    auth_client=Depends(get_supabase_auth),
):
    from app.schemas.common import ok

    service = _service(auth_client)
    session = await service.refresh(payload=payload)
    return ok(session.model_dump(mode="json"))


@router.post(
    "/logout", response_model=ApiResponse[MessageData], summary="Revoke the current session"
)
async def logout(
    user: CurrentUser = Depends(get_current_user),
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    auth_client=Depends(get_supabase_auth),
):
    from app.schemas.common import ok

    service = _service(auth_client)
    await service.logout(credentials.credentials)
    return ok(MessageData(message="Logged out").model_dump())


@router.get("/me", response_model=ApiResponse[MeOut], summary="Current profile")
async def me(
    request: Request,
    user: CurrentUser = Depends(get_current_user),
    conn: asyncpg.Connection = Depends(get_connection),
    auth_client=Depends(get_supabase_auth),
):
    from app.schemas.common import ok

    claims = getattr(request.state, "claims", {})
    service = _service(auth_client)
    profile = await service.me(conn, actor=user, email=claims.get("email"))
    return ok(profile.model_dump(mode="json"))


@router.patch("/me", response_model=ApiResponse[UserOut], summary="Update the current profile")
async def update_me(
    payload: MeUpdate,
    user: CurrentUser = Depends(get_current_user),
    conn: asyncpg.Connection = Depends(get_connection),
    request_info: RequestInfo = Depends(get_request_info),
):
    from app.schemas.common import ok
    from app.schemas.user import UserUpdate

    service = UserService()
    row = await service.update_user(
        conn,
        actor=user,
        user_id=user.id,
        payload=UserUpdate(**payload.model_dump(exclude_unset=True)),
        request=request_info,
    )
    return ok(UserOut.from_record(row).model_dump(mode="json"))
