"""Service-to-service endpoints exposed by core-api."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, Field

from app.core.exceptions import NotFound
from app.core.internal_auth import require_service
from app.db.pool import get_connection
from app.models.entities import ServiceIdentity
from app.repositories.agency_repository import AgencyRepository
from app.repositories.document_repository import DocumentRepository
from app.repositories.verification_repository import VerificationRepository
from app.schemas.common import ok
from app.services.audit_service import AuditService
from app.services.document_service import DocumentService
from app.utils.file_processing import sanitize_filename

router = APIRouter(dependencies=[Depends(require_service)])


@router.get("/documents/{document_id}/content")
async def document_content(
    document_id: UUID,
    identity: ServiceIdentity = Depends(require_service),
    conn: asyncpg.Connection = Depends(get_connection),
):
    service = DocumentService()
    row, content = await service.get_bytes(conn, document_id)
    await service.audit.record(
        conn,
        actor=None,
        action="document.ai_accessed",
        entity_type="document",
        entity_id=document_id,
        metadata={"bytes": len(content), "mime_type": row["mime_type"]},
        actor_service=identity.service,
    )
    filename = sanitize_filename(row["original_filename"])
    return Response(
        content=content,
        media_type=row["mime_type"],
        headers={
            "Content-Disposition": f'inline; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )


@router.get("/agencies/{agency_id}/license-history")
async def agency_license_history(
    agency_id: UUID,
    identity: ServiceIdentity = Depends(require_service),
    conn: asyncpg.Connection = Depends(get_connection),
):
    repo = AgencyRepository()
    agency = await repo.get(conn, agency_id)
    if agency is None:
        raise NotFound("Agency not found")
    history = await repo.list_licenses(conn, agency_id)
    await AuditService().record(
        conn,
        actor=None,
        action="agency.license_history_accessed",
        entity_type="agency",
        entity_id=agency_id,
        metadata={"records": len(history)},
        actor_service=identity.service,
    )
    return ok({"agency": dict(agency), "licenses": [dict(row) for row in history]})


@router.get("/verifications/{verification_id}")
async def verification_context(
    verification_id: UUID,
    identity: ServiceIdentity = Depends(require_service),
    conn: asyncpg.Connection = Depends(get_connection),
):
    row = await VerificationRepository().get(conn, verification_id)
    if row is None:
        raise NotFound("Verification not found")
    documents, _ = await DocumentRepository().list_documents(
        conn,
        user_id=None,
        verification_id=verification_id,
        document_type=None,
        page_size=100,
        offset=0,
        order_by="created_at ASC",
    )
    await AuditService().record(
        conn,
        actor=None,
        action="verification.context_accessed",
        entity_type="verification",
        entity_id=verification_id,
        metadata={"documents": len(documents)},
        actor_service=identity.service,
    )
    return ok(
        {
            "verification": dict(row),
            "documents": [dict(document) for document in documents],
        }
    )


class InternalAuditEvent(BaseModel):
    action: str = Field(max_length=100)
    entity_type: str | None = Field(default=None, max_length=100)
    entity_id: UUID | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


@router.post("/audit-events")
async def forward_audit_event(
    payload: InternalAuditEvent,
    identity: ServiceIdentity = Depends(require_service),
    conn: asyncpg.Connection = Depends(get_connection),
):
    await AuditService().record(
        conn,
        actor=None,
        action=payload.action,
        entity_type=payload.entity_type,
        entity_id=payload.entity_id,
        metadata=payload.metadata,
        actor_service=identity.service,
    )
    return ok({"recorded": True})


health_router = APIRouter()


@health_router.get("/health")
async def internal_health() -> dict[str, str]:
    return {"status": "ok", "service": "core-api", "scope": "internal"}
