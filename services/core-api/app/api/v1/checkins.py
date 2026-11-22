"""Check-in listing, responses, scheduling and staff escalation."""

from __future__ import annotations

from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import JSONResponse

from app.api.dependencies import (
    get_current_user,
    get_idempotency_key,
    get_request_info,
    staff_user,
)
from app.core.idempotency import (
    abort_idempotency,
    begin_idempotency,
    complete_idempotency,
)
from app.db.pool import get_connection
from app.models.entities import CurrentUser, RequestInfo
from app.repositories.migration_repository import CHECKIN_SORT
from app.schemas.common import ApiResponse, PageParams, PageResponse, ok, page_data
from app.schemas.migration import (
    CheckinCreate,
    CheckinEscalate,
    CheckinOut,
    CheckinRespond,
    CheckinUpdate,
)
from app.services.migration_service import MigrationService

router = APIRouter()


@router.get("", response_model=PageResponse[CheckinOut])
async def list_checkins(
    params: PageParams = Depends(),
    user_id: UUID | None = Query(default=None),
    journey_id: UUID | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    overdue_only: bool = Query(default=False),
    user: CurrentUser = Depends(get_current_user),
    conn: asyncpg.Connection = Depends(get_connection),
):
    order_by = params.resolve_sort(CHECKIN_SORT, "due_at")
    rows, total = await MigrationService().list_checkins(
        conn,
        actor=user,
        user_id=user_id,
        journey_id=journey_id,
        status=status_filter,
        overdue_only=overdue_only,
        page_size=params.page_size,
        offset=params.offset,
        order_by=order_by,
    )
    return page_data([CheckinOut.from_record(row) for row in rows], total, params)


@router.get("/overdue", response_model=PageResponse[CheckinOut])
async def list_overdue_checkins(
    params: PageParams = Depends(),
    user: CurrentUser = Depends(staff_user),
    conn: asyncpg.Connection = Depends(get_connection),
):
    order_by = params.resolve_sort(CHECKIN_SORT, "due_at")
    rows, total = await MigrationService().overdue(
        conn,
        actor=user,
        page_size=params.page_size,
        offset=params.offset,
        order_by=order_by.replace("DESC", "ASC"),
    )
    return page_data([CheckinOut.from_record(row) for row in rows], total, params)


@router.post("", response_model=ApiResponse[CheckinOut], status_code=status.HTTP_201_CREATED)
async def schedule_checkin(
    payload: CheckinCreate,
    user: CurrentUser = Depends(staff_user),
    conn: asyncpg.Connection = Depends(get_connection),
    request_info: RequestInfo = Depends(get_request_info),
):
    row = await MigrationService().schedule_checkin(
        conn, actor=user, payload=payload, request=request_info
    )
    return ok(CheckinOut.from_record(row))


@router.get("/{checkin_id}", response_model=ApiResponse[CheckinOut])
async def get_checkin(
    checkin_id: UUID,
    user: CurrentUser = Depends(get_current_user),
    conn: asyncpg.Connection = Depends(get_connection),
):
    row = await MigrationService().get_checkin(conn, actor=user, checkin_id=checkin_id)
    return ok(CheckinOut.from_record(row))


@router.patch("/{checkin_id}", response_model=ApiResponse[CheckinOut])
async def update_checkin(
    checkin_id: UUID,
    payload: CheckinUpdate,
    user: CurrentUser = Depends(staff_user),
    conn: asyncpg.Connection = Depends(get_connection),
    request_info: RequestInfo = Depends(get_request_info),
):
    row = await MigrationService().update_checkin(
        conn, actor=user, checkin_id=checkin_id, payload=payload, request=request_info
    )
    return ok(CheckinOut.from_record(row))


@router.post("/{checkin_id}/respond", response_model=ApiResponse[CheckinOut])
async def respond_to_checkin(
    checkin_id: UUID,
    payload: CheckinRespond,
    request: Request,
    idem_key: str | None = Depends(get_idempotency_key),
    user: CurrentUser = Depends(get_current_user),
    conn: asyncpg.Connection = Depends(get_connection),
    request_info: RequestInfo = Depends(get_request_info),
):
    ctx = await begin_idempotency(
        conn,
        user_id=user.id,
        key=idem_key,
        method="POST",
        path=request.url.path,
        payload=payload.model_dump(mode="json"),
    )
    if not ctx.acquired:
        return JSONResponse(status_code=ctx.status_code, content=ok(ctx.replay))
    try:
        row = await MigrationService().respond(
            conn,
            actor=user,
            checkin_id=checkin_id,
            payload=payload,
            request=request_info,
        )
    except Exception:
        await abort_idempotency(conn, ctx)
        raise
    data = CheckinOut.from_record(row).model_dump(mode="json")
    await complete_idempotency(conn, ctx, data, status_code=200)
    return JSONResponse(status_code=200, content=ok(data))


@router.post("/{checkin_id}/escalate", response_model=ApiResponse[CheckinOut])
async def escalate_checkin(
    checkin_id: UUID,
    payload: CheckinEscalate,
    user: CurrentUser = Depends(staff_user),
    conn: asyncpg.Connection = Depends(get_connection),
    request_info: RequestInfo = Depends(get_request_info),
):
    row = await MigrationService().escalate_checkin(
        conn, actor=user, checkin_id=checkin_id, payload=payload, request=request_info
    )
    return ok(CheckinOut.from_record(row))
