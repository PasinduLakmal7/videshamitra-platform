"""Liveness and readiness."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.db import redis as redis_db
from app.db.pool import ping as db_ping

router = APIRouter()


@router.get("/health", summary="Liveness")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": settings.SERVICE_NAME}


@router.get("/ready", summary="Readiness: DB, Redis, storage and internal clients")
async def ready(request: Request):
    db_ok = await db_ping()
    redis_ok = await redis_db.ping()
    storage = getattr(request.app.state, "storage", None)
    auth = getattr(request.app.state, "supabase_auth", None)
    ai = getattr(request.app.state, "ai_client", None)
    notification = getattr(request.app.state, "notification_client", None)
    storage_ok = await storage.health() if storage else False
    checks = {
        "database": db_ok,
        "redis": redis_ok,
        "storage": storage_ok,
        "supabase_auth": await auth.health() if auth else False,
        "ai_service": await ai.health() if ai else False,
        "notification_service": await notification.health() if notification else False,
    }
    critical = ("database", "redis", "storage")
    healthy = all(checks[name] for name in critical)
    return JSONResponse(
        status_code=200 if healthy else 503,
        content={
            "status": "ok" if healthy else "degraded",
            "service": settings.SERVICE_NAME,
            "environment": settings.ENVIRONMENT,
            "checks": checks,
        },
    )
