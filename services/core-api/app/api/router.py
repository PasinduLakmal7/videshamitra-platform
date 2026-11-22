"""Public API v1 router."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import (
    admin,
    agencies,
    auth,
    chat,
    checkins,
    complaints,
    documents,
    migration,
    notifications,
    users,
    verification,
    webhooks,
)

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["Auth"])
api_router.include_router(users.router, prefix="/users", tags=["Users"])
api_router.include_router(agencies.router, prefix="/agencies", tags=["Agencies"])
api_router.include_router(verification.router, prefix="/verification", tags=["Verification"])
api_router.include_router(documents.router, prefix="/documents", tags=["Documents"])
api_router.include_router(migration.router, prefix="/migration", tags=["Migration"])
api_router.include_router(checkins.router, prefix="/checkins", tags=["Check-ins"])
api_router.include_router(complaints.router, prefix="/complaints", tags=["Complaints"])
api_router.include_router(notifications.router, prefix="/notifications", tags=["Notifications"])
api_router.include_router(admin.router, prefix="/admin", tags=["Admin"])
api_router.include_router(chat.router, prefix="/chat", tags=["Chat"])
api_router.include_router(webhooks.router, prefix="/webhooks", tags=["Webhooks"])
