"""Worker complaints and evidence attachment."""

from __future__ import annotations

from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import JSONResponse

from app.api.dependencies import (
    get_current_user,
    get_idempotency_key,
    get_request_info,
)
from app.core.idempotency import (
    abort_idempotency,
    begin_idempotency,
    complete_idempotency,
)
from app.db.pool import get_connection
from app.models.entities import CurrentUser, RequestInfo
from app.repositories.complaint_repository import SORT_COLUMNS
from app.schemas.common import (
    ApiResponse,
    PageParams,
    PageResponse,
    ok,
    page_data,
)
from app.schemas.complaint import (
    CaseDetail,
    CaseNoteOut,
    ComplaintAttachDocuments,
    ComplaintCreate,
    ComplaintOut,
    ComplaintUpdate,
)
from app.schemas.document import DocumentSummary
from app.schemas.migration import CheckinOut, JourneyOut
from app.schemas.user import UserOut
from app.schemas.verification import VerificationOut
from app.services.complaint_service import ComplaintService

router = APIRouter()


def _detail(detail: dict) -> CaseDetail:
    return CaseDetail(
        case=ComplaintOut.from_record(detail["case"]),
        worker=UserOut.from_record(detail["worker"]) if detail["worker"] else None,
        journey=JourneyOut.from_record(detail["journey"]) if detail["journey"] else None,
        verification=(
            VerificationOut.from_record(detail["verification"]) if detail["verification"] else None
        ),
        checkin=CheckinOut.from_record(detail["checkin"]) if detail["checkin"] else None,
        documents=[DocumentSummary.from_record(row) for row in detail["documents"]],
        notes=[CaseNoteOut.from_record(row) for row in detail["notes"]],
    )


@router.post("", response_model=ApiResponse[ComplaintOut], status_code=status.HTTP_201_CREATED)
async def create_complaint(
    payload: ComplaintCreate,
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
        row = await ComplaintService().create(
            conn, actor=user, payload=payload, request=request_info
        )
    except Exception:
        await abort_idempotency(conn, ctx)
        raise
    data = ComplaintOut.from_record(row).model_dump(mode="json")
    await complete_idempotency(conn, ctx, data, status_code=201)
    return JSONResponse(status_code=201, content=ok(data))


@router.get("", response_model=PageResponse[ComplaintOut])
async def list_complaints(
    params: PageParams = Depends(),
    user_id: UUID | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    triage_tier: int | None = Query(default=None, ge=1, le=3),
    assigned_to: UUID | None = Query(default=None),
    q: str | None = Query(default=None, max_length=200),
    user: CurrentUser = Depends(get_current_user),
    conn: asyncpg.Connection = Depends(get_connection),
):
    order_by = params.resolve_sort(SORT_COLUMNS, "created_at")
    rows, total = await ComplaintService().list_complaints(
        conn,
        actor=user,
        user_id=user_id,
        status=status_filter,
        triage_tier=triage_tier,
        assigned_to=assigned_to,
        q=q,
        page_size=params.page_size,
        offset=params.offset,
        order_by=order_by,
    )
    return page_data([ComplaintOut.from_record(row) for row in rows], total, params)


@router.get("/{complaint_id}", response_model=ApiResponse[CaseDetail])
async def get_complaint(
    complaint_id: UUID,
    user: CurrentUser = Depends(get_current_user),
    conn: asyncpg.Connection = Depends(get_connection),
):
    detail = await ComplaintService().detail(conn, actor=user, complaint_id=complaint_id)
    return ok(_detail(detail))


@router.patch("/{complaint_id}", response_model=ApiResponse[ComplaintOut])
async def update_complaint(
    complaint_id: UUID,
    payload: ComplaintUpdate,
    user: CurrentUser = Depends(get_current_user),
    conn: asyncpg.Connection = Depends(get_connection),
    request_info: RequestInfo = Depends(get_request_info),
):
    row = await ComplaintService().update(
        conn,
        actor=user,
        complaint_id=complaint_id,
        payload=payload,
        request=request_info,
    )
    return ok(ComplaintOut.from_record(row))


@router.post("/{complaint_id}/submit", response_model=ApiResponse[ComplaintOut])
async def submit_complaint(
    complaint_id: UUID,
    user: CurrentUser = Depends(get_current_user),
    conn: asyncpg.Connection = Depends(get_connection),
    request_info: RequestInfo = Depends(get_request_info),
):
    row = await ComplaintService().submit(
        conn, actor=user, complaint_id=complaint_id, request=request_info
    )
    return ok(ComplaintOut.from_record(row))


@router.post("/{complaint_id}/documents", response_model=ApiResponse[ComplaintOut])
async def attach_documents(
    complaint_id: UUID,
    payload: ComplaintAttachDocuments,
    user: CurrentUser = Depends(get_current_user),
    conn: asyncpg.Connection = Depends(get_connection),
    request_info: RequestInfo = Depends(get_request_info),
):
    row = await ComplaintService().attach_documents(
        conn,
        actor=user,
        complaint_id=complaint_id,
        document_ids=payload.document_ids,
        request=request_info,
    )
    return ok(ComplaintOut.from_record(row))
