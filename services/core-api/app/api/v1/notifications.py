"""In-app notification feed and notification-service proxies."""

from __future__ import annotations

from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, Query

from app.api.dependencies import (
    get_current_user,
    get_notification_client,
)
from app.db.pool import get_connection
from app.models.entities import CurrentUser
from app.repositories.notification_repository import SORT_COLUMNS
from app.schemas.common import (
    ApiResponse,
    CountData,
    PageParams,
    PageResponse,
    ok,
    page_data,
)
from app.schemas.notification import (
    DeviceRegister,
    NotificationOut,
    PreferencesUpdate,
)
from app.services.notification_service import NotificationService

router = APIRouter()


@router.get("", response_model=PageResponse[NotificationOut])
async def list_notifications(
    params: PageParams = Depends(),
    type_filter: str | None = Query(default=None, alias="type"),
    unread_only: bool = Query(default=False),
    user: CurrentUser = Depends(get_current_user),
    conn: asyncpg.Connection = Depends(get_connection),
):
    order_by = params.resolve_sort(SORT_COLUMNS, "created_at")
    rows, total = await NotificationService().list_feed(
        conn,
        user_id=user.id,
        notification_type=type_filter,
        unread_only=unread_only,
        page_size=params.page_size,
        offset=params.offset,
        order_by=order_by,
    )
    return page_data([NotificationOut.from_record(row) for row in rows], total, params)


@router.get("/unread-count", response_model=ApiResponse[CountData])
async def unread_count(
    user: CurrentUser = Depends(get_current_user),
    conn: asyncpg.Connection = Depends(get_connection),
):
    count = await NotificationService().unread_count(conn, user.id)
    return ok(CountData(count=count))


@router.post("/read-all", response_model=ApiResponse[CountData])
async def mark_all_read(
    user: CurrentUser = Depends(get_current_user),
    conn: asyncpg.Connection = Depends(get_connection),
):
    count = await NotificationService().mark_all_read(conn, user.id)
    return ok(CountData(count=count))


@router.patch("/{notification_id}/read", response_model=ApiResponse[NotificationOut])
async def mark_read(
    notification_id: UUID,
    user: CurrentUser = Depends(get_current_user),
    conn: asyncpg.Connection = Depends(get_connection),
):
    row = await NotificationService().mark_read(
        conn, user_id=user.id, notification_id=notification_id
    )
    return ok(NotificationOut.from_record(row))


@router.post("/devices", response_model=ApiResponse[dict])
async def register_device(
    payload: DeviceRegister,
    user: CurrentUser = Depends(get_current_user),
    client=Depends(get_notification_client),
):
    result = await NotificationService(client=client).register_device(
        user.id, payload.model_dump(exclude_none=True)
    )
    return ok(result)


@router.delete("/devices/{token}", response_model=ApiResponse[dict])
async def unregister_device(
    token: str,
    user: CurrentUser = Depends(get_current_user),
    client=Depends(get_notification_client),
):
    result = await NotificationService(client=client).unregister_device(user.id, token)
    return ok(result)


@router.get("/preferences", response_model=ApiResponse[dict])
async def get_preferences(
    user: CurrentUser = Depends(get_current_user),
    client=Depends(get_notification_client),
):
    result = await NotificationService(client=client).get_preferences(user.id)
    return ok(result)


@router.patch("/preferences", response_model=ApiResponse[dict])
async def update_preferences(
    payload: PreferencesUpdate,
    user: CurrentUser = Depends(get_current_user),
    client=Depends(get_notification_client),
):
    result = await NotificationService(client=client).update_preferences(
        user.id, payload.model_dump(exclude_none=True)
    )
    return ok(result)
