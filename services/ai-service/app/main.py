"""ai-service application factory (internal network only)."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import APIRouter, Depends, FastAPI

from app.clients.core_api import CoreApiClient
from app.core.config import settings
from app.core.errors import register_exception_handlers
from app.core.internal_auth import require_core
from app.core.logging import setup_logging
from app.core.request_id import RequestContextMiddleware

logger = logging.getLogger(__name__)

INTERNAL_PREFIX = "/internal/v1"

health_router = APIRouter()
# Every internal route except health mounts here so it inherits the core token check.
internal_router = APIRouter(dependencies=[Depends(require_core)])


@health_router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    logger.info("ai_service_starting", extra={"environment": settings.ENVIRONMENT})
    app.state.core_api = CoreApiClient()
    try:
        yield
    finally:
        await app.state.core_api.aclose()
        logger.info("ai_service_stopped")


def create_app() -> FastAPI:
    app = FastAPI(
        title="VideshaMitra AI Service",
        version=settings.VERSION,
        lifespan=lifespan,
        docs_url=None if settings.ENVIRONMENT == "production" else "/docs",
        redoc_url=None,
        openapi_url=None if settings.ENVIRONMENT == "production" else "/openapi.json",
    )
    app.add_middleware(RequestContextMiddleware)
    register_exception_handlers(app)
    app.include_router(health_router, prefix=INTERNAL_PREFIX)
    app.include_router(internal_router, prefix=INTERNAL_PREFIX)
    return app


app = create_app()
