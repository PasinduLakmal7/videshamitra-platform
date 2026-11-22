"""User profile and consent endpoints."""

from __future__ import annotations

from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, Query

from app.api.dependencies import admin_user, get_current_user, get_request_info, staff_user
from app.db.pool import get_connection
from app.models.entities import CurrentUser, RequestInfo
from app.models.enums import UserRole
from app.repositories.user_repository import SORT_COLUMNS
from app.schemas.common import ApiResponse, PageParams, PageResponse, ok, page_data
from app.schemas.user import (
    ConsentCreate,
    ConsentOut,
    RoleUpdate,
    StatusUpdate,
    UserOut,
    UserUpdate,
)
from app.services.user_service import UserService

router = APIRouter()


@router.get("", response_model=PageResponse[UserOut])
async def list_users(
    params: PageParams = Depends(),
    role: UserRole | None = Query(default=None),
    q: str | None = Query(default=None, max_length=200),
    is_active: bool | None = Query(default=None),
    user: CurrentUser = Depends(staff_user),
    conn: asyncpg.Connection = Depends(get_connection),
):
    order_by = params.resolve_sort(SORT_COLUMNS, "created_at")
    rows, total = await UserService().list_users(
        conn,
        actor=user,
        page=params.page,
        page_size=params.page_size,
        offset=params.offset,
        order_by=order_by,
        role=role.value if role else None,
        q=q,
        is_active=is_active,
    )
    return page_data([UserOut.from_record(row) for row in rows], total, params)


@router.get("/me/consents", response_model=ApiResponse[list[ConsentOut]])
async def list_my_consents(
    user: CurrentUser = Depends(get_current_user),
    conn: asyncpg.Connection = Depends(get_connection),
):
    rows = await UserService().list_consents(conn, actor=user)
    return ok([ConsentOut.from_record(row) for row in rows])


@router.post("/me/consents", response_model=ApiResponse[ConsentOut], status_code=201)
async def create_my_consent(
    payload: ConsentCreate,
    user: CurrentUser = Depends(get_current_user),
    conn: asyncpg.Connection = Depends(get_connection),
    request_info: RequestInfo = Depends(get_request_info),
):
    row = await UserService().create_consent(
        conn, actor=user, payload=payload, request=request_info
    )
    return ok(ConsentOut.from_record(row))


@router.get("/{user_id}", response_model=ApiResponse[UserOut])
async def get_user(
    user_id: UUID,
    user: CurrentUser = Depends(get_current_user),
    conn: asyncpg.Connection = Depends(get_connection),
):
    row = await UserService().get_user(conn, actor=user, user_id=user_id)
    return ok(UserOut.from_record(row))


@router.patch("/{user_id}", response_model=ApiResponse[UserOut])
async def update_user(
    user_id: UUID,
    payload: UserUpdate,
    user: CurrentUser = Depends(get_current_user),
    conn: asyncpg.Connection = Depends(get_connection),
    request_info: RequestInfo = Depends(get_request_info),
):
    row = await UserService().update_user(
        conn, actor=user, user_id=user_id, payload=payload, request=request_info
    )
    return ok(UserOut.from_record(row))


@router.patch("/{user_id}/role", response_model=ApiResponse[UserOut])
async def update_role(
    user_id: UUID,
    payload: RoleUpdate,
    user: CurrentUser = Depends(admin_user),
    conn: asyncpg.Connection = Depends(get_connection),
    request_info: RequestInfo = Depends(get_request_info),
):
    row = await UserService().update_role(
        conn, actor=user, user_id=user_id, role=payload.role, request=request_info
    )
    return ok(UserOut.from_record(row))


@router.patch("/{user_id}/status", response_model=ApiResponse[UserOut])
async def update_status(
    user_id: UUID,
    payload: StatusUpdate,
    user: CurrentUser = Depends(admin_user),
    conn: asyncpg.Connection = Depends(get_connection),
    request_info: RequestInfo = Depends(get_request_info),
):
    row = await UserService().update_status(
        conn,
        actor=user,
        user_id=user_id,
        is_active=payload.is_active,
        request=request_info,
    )
    return ok(UserOut.from_record(row))
