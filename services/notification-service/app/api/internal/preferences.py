"""Notification preferences."""

from __future__ import annotations

from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends

from app.api.dependencies import get_connection
from app.schemas.preference import PreferencesUpdate
from app.services.preference_service import PreferenceService

router = APIRouter()


@router.get("/preferences/{user_id}")
async def get_preferences(
    user_id: UUID,
    conn: asyncpg.Connection = Depends(get_connection),
):
    prefs = await PreferenceService().get(conn, user_id)
    return {"preferences": prefs.model_dump(mode="json")}


@router.put("/preferences/{user_id}")
async def update_preferences(
    user_id: UUID,
    payload: PreferencesUpdate,
    conn: asyncpg.Connection = Depends(get_connection),
):
    prefs = await PreferenceService().update(conn, user_id, payload)
    return {"preferences": prefs.model_dump(mode="json")}
