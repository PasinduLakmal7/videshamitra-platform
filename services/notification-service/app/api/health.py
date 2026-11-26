"""Liveness and readiness."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.db import redis as redis_db
from app.db.pool import ping as db_ping

router = APIRouter()


@router.get("/health", summary="Liveness")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": settings.SERVICE_NAME}


@router.get("/ready", summary="Readiness: Postgres and Redis")
async def ready():
    checks = {
        "database": await db_ping(),
        "redis": await redis_db.ping(),
    }
    healthy = all(checks.values())
    return JSONResponse(
        status_code=200 if healthy else 503,
        content={
            "status": "ok" if healthy else "degraded",
            "service": settings.SERVICE_NAME,
            "checks": checks,
        },
    )
