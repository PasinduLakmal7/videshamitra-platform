"""VideshaMitra notification-service application factory (internal only)."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.health import router as health_router
from app.api.internal.health import router as internal_health_router
from app.api.internal.router import router as internal_router
from app.core.config import settings
from app.core.errors import register_exception_handlers
from app.core.logging import setup_logging
from app.core.request_id import RequestContextMiddleware
from app.db import redis as redis_db
from app.db.pool import close_pool, create_pool

logger = logging.getLogger(__name__)

INTERNAL_PREFIX = "/internal/v1"


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    logger.info("notification_service_starting", extra={"environment": settings.ENVIRONMENT})
    app.state.pool = await create_pool()
    app.state.redis = redis_db.create_client()
    logger.info("notification_service_ready")
    try:
        yield
    finally:
        logger.info("notification_service_stopping")
        await redis_db.close_client()
        await close_pool()


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.PROJECT_NAME,
        version=settings.VERSION,
        description="Internal notification delivery service. Not exposed through Kong.",
        docs_url=None if settings.ENVIRONMENT == "production" else "/docs",
        redoc_url=None,
        openapi_url=None if settings.ENVIRONMENT == "production" else "/openapi.json",
        lifespan=lifespan,
    )
    app.add_middleware(RequestContextMiddleware)
    register_exception_handlers(app)
    app.include_router(health_router)
    app.include_router(internal_health_router, prefix=INTERNAL_PREFIX)
    app.include_router(internal_router, prefix=INTERNAL_PREFIX)
    return app


app = create_app()
