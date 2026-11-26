"""Device registration and unregistration."""

from __future__ import annotations

from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, Query

from app.api.dependencies import get_connection
from app.schemas.device import DeviceOut, DeviceRegisterRequest
from app.services.device_service import DeviceService

router = APIRouter()


@router.post("/devices")
async def register_device(
    payload: DeviceRegisterRequest,
    conn: asyncpg.Connection = Depends(get_connection),
):
    row = await DeviceService().register(
        conn,
        user_id=payload.user_id,
        token=payload.token,
        platform=payload.platform,
        app_version=payload.app_version,
        device_id=payload.device_id,
        locale=payload.locale,
    )
    return {"device": DeviceOut.from_record(row).model_dump(mode="json")}


@router.delete("/devices/{token}")
async def unregister_device(
    token: str,
    user_id: UUID = Query(...),
    conn: asyncpg.Connection = Depends(get_connection),
):
    await DeviceService().unregister(conn, user_id=user_id, token=token)
    return {"unregistered": True}
