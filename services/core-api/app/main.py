"""VideshaMitra core-api application factory."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.errors import register_exception_handlers
from app.api.health import router as health_router
from app.api.internal.router import health_router as internal_health_router
from app.api.internal.router import router as internal_router
from app.api.router import api_router
from app.core.config import settings
from app.core.logging import setup_logging
from app.core.request_id import RequestContextMiddleware
from app.db import redis as redis_db
from app.db.pool import close_pool, create_pool
from app.integrations.ai_client import AIClient
from app.integrations.notification_client import NotificationClient
from app.integrations.supabase.auth import SupabaseAuthClient
from app.integrations.supabase.storage import SupabaseStorage

logger = logging.getLogger(__name__)

TAGS_METADATA = [
    {"name": "Auth", "description": "Supabase-backed registration, login and OTP"},
    {"name": "Users", "description": "Profiles, consents and staff user management"},
    {"name": "Agencies", "description": "SLBFE agency search, licenses and imports"},
    {"name": "Verification", "description": "Async AI-assisted verification orchestration"},
    {"name": "Documents", "description": "Private document upload and signed downloads"},
    {"name": "Migration", "description": "Journey stages and check-in consent"},
    {"name": "Check-ins", "description": "Day 7/30/90 safety check-ins and escalation"},
    {"name": "Complaints", "description": "Worker complaints and evidence"},
    {"name": "Notifications", "description": "In-app feed and device/preference proxies"},
    {"name": "Admin", "description": "Caseworker dashboard, cases, traces and audit"},
    {"name": "Chat", "description": "Chat and speech proxied to ai-service"},
    {"name": "Webhooks", "description": "Signed provider callbacks"},
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    logger.info("core_api_starting", extra={"environment": settings.ENVIRONMENT})
    app.state.pool = await create_pool()
    app.state.redis = redis_db.create_client()
    app.state.storage = SupabaseStorage()
    app.state.supabase_auth = SupabaseAuthClient()
    app.state.ai_client = AIClient(settings.AI_SERVICE_URL)
    app.state.notification_client = NotificationClient(settings.NOTIFICATION_SERVICE_URL)
    logger.info("core_api_ready")
    try:
        yield
    finally:
        logger.info("core_api_stopping")
        for name in (
            "ai_client",
            "notification_client",
            "storage",
            "supabase_auth",
        ):
            client = getattr(app.state, name, None)
            if client is not None:
                try:
                    await client.aclose()
                except Exception:  # pragma: no cover - shutdown best effort
                    logger.exception("client_close_failed", extra={"client": name})
        await redis_db.close_client()
        await close_pool()
        logger.info("core_api_stopped")


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.PROJECT_NAME,
        version=settings.VERSION,
        description=(
            "Public API for VideshaMitra. All clients use /api/v1; "
            "ai-service and notification-service are internal."
        ),
        openapi_tags=TAGS_METADATA,
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID", "X-Trace-ID"],
    )
    app.add_middleware(RequestContextMiddleware, logger=logging.getLogger("access"))
    register_exception_handlers(app)

    app.include_router(health_router)
    app.include_router(api_router, prefix=settings.API_V1_STR)
    app.include_router(internal_router, prefix="/internal/v1", tags=["Internal"])
    app.include_router(internal_health_router, prefix="/internal/v1", tags=["Internal"])
    return app


app = create_app()
