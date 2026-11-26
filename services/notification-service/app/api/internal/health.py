"""Internal health endpoint for core readiness probes."""

from __future__ import annotations

from fastapi import APIRouter

from app.core.config import settings

router = APIRouter()


@router.get("/health", summary="Internal liveness")
async def internal_health() -> dict[str, str]:
    return {"status": "ok", "service": settings.SERVICE_NAME, "scope": "internal"}
