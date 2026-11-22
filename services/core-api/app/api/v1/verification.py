"""Verification creation/list/get/retry/review."""

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
from app.repositories.verification_repository import SORT_COLUMNS
from app.schemas.common import ApiResponse, PageParams, PageResponse, ok, page_data
from app.schemas.verification import (
    VerificationCreate,
    VerificationOut,
    VerificationReview,
)
from app.services.verification_service import VerificationService

router = APIRouter()


@router.post(
    "",
    response_model=ApiResponse[VerificationOut],
    status_code=status.HTTP_202_ACCEPTED,
    summary="Create a verification and queue AI analysis",
)
async def create_verification(
    payload: VerificationCreate,
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
        row = await VerificationService().create(
            conn, actor=user, payload=payload, request=request_info
        )
    except Exception:
        await abort_idempotency(conn, ctx)
        raise
    data = VerificationOut.from_record(row).model_dump(mode="json")
    await complete_idempotency(conn, ctx, data, status_code=202)
    return JSONResponse(status_code=202, content=ok(data))


@router.get("", response_model=PageResponse[VerificationOut])
async def list_verifications(
    params: PageParams = Depends(),
    user_id: UUID | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    risk_level: str | None = Query(default=None),
    agency_id: UUID | None = Query(default=None),
    q: str | None = Query(default=None, max_length=200),
    user: CurrentUser = Depends(get_current_user),
    conn: asyncpg.Connection = Depends(get_connection),
):
    order_by = params.resolve_sort(SORT_COLUMNS, "created_at")
    rows, total = await VerificationService().list_verifications(
        conn,
        actor=user,
        user_id=user_id,
        status=status_filter,
        risk_level=risk_level,
        agency_id=agency_id,
        q=q,
        page_size=params.page_size,
        offset=params.offset,
        order_by=order_by,
    )
    return page_data([VerificationOut.from_record(row) for row in rows], total, params)


@router.get("/{verification_id}", response_model=ApiResponse[VerificationOut])
async def get_verification(
    verification_id: UUID,
    user: CurrentUser = Depends(get_current_user),
    conn: asyncpg.Connection = Depends(get_connection),
):
    row = await VerificationService().get(conn, actor=user, verification_id=verification_id)
    return ok(VerificationOut.from_record(row))


@router.post(
    "/{verification_id}/retry", response_model=ApiResponse[VerificationOut], status_code=202
)
async def retry_verification(
    verification_id: UUID,
    user: CurrentUser = Depends(get_current_user),
    conn: asyncpg.Connection = Depends(get_connection),
    request_info: RequestInfo = Depends(get_request_info),
):
    row = await VerificationService().retry(
        conn,
        actor=user,
        verification_id=verification_id,
        request=request_info,
    )
    return ok(VerificationOut.from_record(row))


@router.patch("/{verification_id}/review", response_model=ApiResponse[VerificationOut])
async def review_verification(
    verification_id: UUID,
    payload: VerificationReview,
    user: CurrentUser = Depends(staff_user),
    conn: asyncpg.Connection = Depends(get_connection),
    request_info: RequestInfo = Depends(get_request_info),
):
    row = await VerificationService().review(
        conn,
        actor=user,
        verification_id=verification_id,
        payload=payload,
        request=request_info,
    )
    return ok(VerificationOut.from_record(row))
