"""Authenticated internal routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.internal import devices, preferences
from app.core.internal_auth import require_core

router = APIRouter(dependencies=[Depends(require_core)])
router.include_router(devices.router)
router.include_router(preferences.router)
