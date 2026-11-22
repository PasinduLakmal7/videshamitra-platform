"""Agency search, detail, license history and admin imports."""

from __future__ import annotations

from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, Query, status

from app.api.dependencies import admin_user, get_current_user, get_request_info
from app.db.pool import get_connection
from app.models.entities import CurrentUser, RequestInfo
from app.models.enums import AgencyLicenseStatus
from app.repositories.agency_repository import SORT_COLUMNS
from app.schemas.agency import (
    AgencyCreate,
    AgencyImportRequest,
    AgencyOut,
    AgencyUpdate,
    ImportResult,
    LicenseHistoryOut,
    SnapshotOut,
)
from app.schemas.common import ApiResponse, PageParams, PageResponse, ok, page_data
from app.services.agency_service import AgencyService

router = APIRouter()


@router.get("", response_model=PageResponse[AgencyOut])
async def search_agencies(
    params: PageParams = Depends(),
    q: str | None = Query(default=None, max_length=200),
    status_filter: AgencyLicenseStatus | None = Query(default=None, alias="status"),
    district: str | None = Query(default=None, max_length=100),
    user: CurrentUser = Depends(get_current_user),
    conn: asyncpg.Connection = Depends(get_connection),
):
    order_by = None
    if params.sort:
        order_by = params.resolve_sort(SORT_COLUMNS, "name")
    rows, total = await AgencyService().search(
        conn,
        q=q,
        status=status_filter.value if status_filter else None,
        district=district,
        page_size=params.page_size,
        offset=params.offset,
        order_by=order_by,
    )
    return page_data([AgencyOut.from_record(row) for row in rows], total, params)


@router.get("/snapshots", response_model=PageResponse[SnapshotOut])
async def list_snapshots(
    params: PageParams = Depends(),
    user: CurrentUser = Depends(admin_user),
    conn: asyncpg.Connection = Depends(get_connection),
):
    rows, total = await AgencyService().list_snapshots(
        conn, page_size=params.page_size, offset=params.offset
    )
    return page_data([SnapshotOut.from_record(row) for row in rows], total, params)


@router.post("", response_model=ApiResponse[AgencyOut], status_code=status.HTTP_201_CREATED)
async def create_agency(
    payload: AgencyCreate,
    user: CurrentUser = Depends(admin_user),
    conn: asyncpg.Connection = Depends(get_connection),
    request_info: RequestInfo = Depends(get_request_info),
):
    row = await AgencyService().create(conn, actor=user, payload=payload, request=request_info)
    return ok(AgencyOut.from_record(row))


@router.post("/import", response_model=ApiResponse[ImportResult])
async def import_agencies(
    payload: AgencyImportRequest,
    user: CurrentUser = Depends(admin_user),
    conn: asyncpg.Connection = Depends(get_connection),
    request_info: RequestInfo = Depends(get_request_info),
):
    summary = await AgencyService().import_agencies(
        conn,
        actor=user,
        snapshot_date=payload.snapshot_date,
        dry_run=payload.dry_run,
        request=request_info,
    )
    return ok(ImportResult(**summary.as_dict()))


@router.get("/{agency_id}", response_model=ApiResponse[AgencyOut])
async def get_agency(
    agency_id: UUID,
    user: CurrentUser = Depends(get_current_user),
    conn: asyncpg.Connection = Depends(get_connection),
):
    row = await AgencyService().get(conn, agency_id)
    return ok(AgencyOut.from_record(row))


@router.get("/{agency_id}/licenses", response_model=ApiResponse[list[LicenseHistoryOut]])
async def get_agency_licenses(
    agency_id: UUID,
    user: CurrentUser = Depends(get_current_user),
    conn: asyncpg.Connection = Depends(get_connection),
):
    rows = await AgencyService().license_history(conn, agency_id)
    return ok([LicenseHistoryOut.from_record(row) for row in rows])


@router.patch("/{agency_id}", response_model=ApiResponse[AgencyOut])
async def update_agency(
    agency_id: UUID,
    payload: AgencyUpdate,
    user: CurrentUser = Depends(admin_user),
    conn: asyncpg.Connection = Depends(get_connection),
    request_info: RequestInfo = Depends(get_request_info),
):
    row = await AgencyService().update(
        conn, actor=user, agency_id=agency_id, payload=payload, request=request_info
    )
    return ok(AgencyOut.from_record(row))
