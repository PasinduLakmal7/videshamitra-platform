"""Migration journey endpoints."""

from __future__ import annotations

from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, Query, status

from app.api.dependencies import get_current_user, get_request_info, staff_user
from app.db.pool import get_connection
from app.models.entities import CurrentUser, RequestInfo
from app.models.enums import JourneyStage
from app.repositories.migration_repository import JOURNEY_SORT
from app.schemas.common import ApiResponse, PageParams, PageResponse, ok, page_data
from app.schemas.migration import (
    JourneyConsent,
    JourneyCreate,
    JourneyOut,
    JourneyStageUpdate,
    JourneyUpdate,
)
from app.services.migration_service import MigrationService

router = APIRouter()


@router.get("/journeys", response_model=PageResponse[JourneyOut])
async def list_journeys(
    params: PageParams = Depends(),
    user_id: UUID | None = Query(default=None),
    stage: JourneyStage | None = Query(default=None),
    user: CurrentUser = Depends(get_current_user),
    conn: asyncpg.Connection = Depends(get_connection),
):
    order_by = params.resolve_sort(JOURNEY_SORT, "created_at")
    rows, total = await MigrationService().list_journeys(
        conn,
        actor=user,
        user_id=user_id,
        stage=stage.value if stage else None,
        page_size=params.page_size,
        offset=params.offset,
        order_by=order_by,
    )
    return page_data([JourneyOut.from_record(row) for row in rows], total, params)


@router.post(
    "/journeys", response_model=ApiResponse[JourneyOut], status_code=status.HTTP_201_CREATED
)
async def create_journey(
    payload: JourneyCreate,
    user: CurrentUser = Depends(get_current_user),
    conn: asyncpg.Connection = Depends(get_connection),
    request_info: RequestInfo = Depends(get_request_info),
):
    row = await MigrationService().create_journey(
        conn, actor=user, payload=payload, request=request_info
    )
    return ok(JourneyOut.from_record(row))


@router.get("/journeys/{journey_id}", response_model=ApiResponse[JourneyOut])
async def get_journey(
    journey_id: UUID,
    user: CurrentUser = Depends(get_current_user),
    conn: asyncpg.Connection = Depends(get_connection),
):
    row = await MigrationService().get_journey(conn, actor=user, journey_id=journey_id)
    return ok(JourneyOut.from_record(row))


@router.patch("/journeys/{journey_id}", response_model=ApiResponse[JourneyOut])
async def update_journey(
    journey_id: UUID,
    payload: JourneyUpdate,
    user: CurrentUser = Depends(get_current_user),
    conn: asyncpg.Connection = Depends(get_connection),
    request_info: RequestInfo = Depends(get_request_info),
):
    row = await MigrationService().update_journey(
        conn, actor=user, journey_id=journey_id, payload=payload, request=request_info
    )
    return ok(JourneyOut.from_record(row))


@router.post("/journeys/{journey_id}/consent", response_model=ApiResponse[JourneyOut])
async def set_consent(
    journey_id: UUID,
    payload: JourneyConsent,
    user: CurrentUser = Depends(get_current_user),
    conn: asyncpg.Connection = Depends(get_connection),
    request_info: RequestInfo = Depends(get_request_info),
):
    row = await MigrationService().set_consent(
        conn, actor=user, journey_id=journey_id, payload=payload, request=request_info
    )
    return ok(JourneyOut.from_record(row))


@router.patch("/journeys/{journey_id}/stage", response_model=ApiResponse[JourneyOut])
async def update_stage(
    journey_id: UUID,
    payload: JourneyStageUpdate,
    user: CurrentUser = Depends(staff_user),
    conn: asyncpg.Connection = Depends(get_connection),
    request_info: RequestInfo = Depends(get_request_info),
):
    row = await MigrationService().update_stage(
        conn,
        actor=user,
        journey_id=journey_id,
        stage=payload.stage,
        request=request_info,
    )
    return ok(JourneyOut.from_record(row))
