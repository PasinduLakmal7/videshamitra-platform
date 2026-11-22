"""Admin dashboard, case queue/detail, notes, escalation, traces and audit."""

from __future__ import annotations

from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, Query

from app.api.dependencies import (
    admin_user,
    get_ai_client,
    get_request_info,
    staff_user,
)
from app.api.v1.complaints import _detail
from app.db.pool import get_connection
from app.models.entities import CurrentUser, RequestInfo
from app.repositories.complaint_repository import SORT_COLUMNS
from app.schemas.admin import AuditLogOut, DashboardOut
from app.schemas.common import ApiResponse, PageParams, PageResponse, ok, page_data
from app.schemas.complaint import (
    CaseDetail,
    CaseEscalate,
    CaseNoteCreate,
    CaseNoteOut,
    CaseUpdate,
    ComplaintOut,
)
from app.services.admin_service import AdminService
from app.services.audit_service import AuditService
from app.services.case_service import CaseService

router = APIRouter()


@router.get("/dashboard", response_model=ApiResponse[DashboardOut])
async def dashboard(
    user: CurrentUser = Depends(staff_user),
    conn: asyncpg.Connection = Depends(get_connection),
):
    data = await AdminService().dashboard(conn, actor=user)
    return ok(data)


@router.get("/cases", response_model=PageResponse[ComplaintOut])
async def list_cases(
    params: PageParams = Depends(),
    status_filter: str | None = Query(default=None, alias="status"),
    triage_tier: int | None = Query(default=None, ge=1, le=3),
    assigned_to: UUID | None = Query(default=None),
    q: str | None = Query(default=None, max_length=200),
    user: CurrentUser = Depends(staff_user),
    conn: asyncpg.Connection = Depends(get_connection),
):
    order_by = params.resolve_sort(SORT_COLUMNS, "created_at")
    rows, total = await CaseService().list_cases(
        conn,
        actor=user,
        status=status_filter,
        triage_tier=triage_tier,
        assigned_to=assigned_to,
        q=q,
        page_size=params.page_size,
        offset=params.offset,
        order_by=order_by,
    )
    return page_data([ComplaintOut.from_record(row) for row in rows], total, params)


@router.get("/cases/{case_id}", response_model=ApiResponse[CaseDetail])
async def get_case(
    case_id: UUID,
    user: CurrentUser = Depends(staff_user),
    conn: asyncpg.Connection = Depends(get_connection),
):
    detail = await CaseService().detail(conn, actor=user, complaint_id=case_id)
    return ok(_detail(detail))


@router.patch("/cases/{case_id}", response_model=ApiResponse[ComplaintOut])
async def update_case(
    case_id: UUID,
    payload: CaseUpdate,
    user: CurrentUser = Depends(staff_user),
    conn: asyncpg.Connection = Depends(get_connection),
    request_info: RequestInfo = Depends(get_request_info),
):
    row = await CaseService().update_case(
        conn, actor=user, complaint_id=case_id, payload=payload, request=request_info
    )
    return ok(ComplaintOut.from_record(row))


@router.get("/cases/{case_id}/notes", response_model=ApiResponse[list[CaseNoteOut]])
async def list_notes(
    case_id: UUID,
    user: CurrentUser = Depends(staff_user),
    conn: asyncpg.Connection = Depends(get_connection),
):
    detail = await CaseService().detail(conn, actor=user, complaint_id=case_id)
    return ok([CaseNoteOut.from_record(row) for row in detail["notes"]])


@router.post("/cases/{case_id}/notes", response_model=ApiResponse[CaseNoteOut], status_code=201)
async def add_note(
    case_id: UUID,
    payload: CaseNoteCreate,
    user: CurrentUser = Depends(staff_user),
    conn: asyncpg.Connection = Depends(get_connection),
    request_info: RequestInfo = Depends(get_request_info),
):
    row = await CaseService().add_note(
        conn, actor=user, complaint_id=case_id, payload=payload, request=request_info
    )
    return ok(CaseNoteOut.from_record(row))


@router.post("/cases/{case_id}/escalate", response_model=ApiResponse[ComplaintOut])
async def escalate_case(
    case_id: UUID,
    payload: CaseEscalate,
    user: CurrentUser = Depends(staff_user),
    conn: asyncpg.Connection = Depends(get_connection),
    request_info: RequestInfo = Depends(get_request_info),
):
    row = await CaseService().escalate_case(
        conn, actor=user, complaint_id=case_id, payload=payload, request=request_info
    )
    return ok(ComplaintOut.from_record(row))


@router.get("/verifications/{verification_id}/trace", response_model=ApiResponse[dict])
async def verification_trace(
    verification_id: UUID,
    user: CurrentUser = Depends(staff_user),
    conn: asyncpg.Connection = Depends(get_connection),
    request_info: RequestInfo = Depends(get_request_info),
    ai_client=Depends(get_ai_client),
):
    data = await AdminService(ai_client=ai_client).trace(
        actor=user, verification_id=verification_id
    )
    await AuditService().record(
        conn,
        actor=user,
        action="verification.trace_accessed",
        entity_type="verification",
        entity_id=verification_id,
        request=request_info,
    )
    return ok(data)


@router.get("/audit-logs", response_model=PageResponse[AuditLogOut])
async def audit_logs(
    params: PageParams = Depends(),
    actor_id: UUID | None = Query(default=None),
    action: str | None = Query(default=None, max_length=100),
    entity_type: str | None = Query(default=None, max_length=100),
    entity_id: UUID | None = Query(default=None),
    user: CurrentUser = Depends(admin_user),
    conn: asyncpg.Connection = Depends(get_connection),
):
    rows, total = await AdminService().audit_logs(
        conn,
        actor=user,
        actor_id=actor_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        page_size=params.page_size,
        offset=params.offset,
    )
    return page_data([AuditLogOut.from_record(row) for row in rows], total, params)
