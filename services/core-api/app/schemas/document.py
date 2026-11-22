"""Document DTOs."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from app.models.enums import DocumentStatus, DocumentType
from app.schemas.base import APIModel


class DocumentOut(APIModel):
    id: UUID
    user_id: UUID
    verification_id: UUID | None = None
    type: DocumentType
    status: DocumentStatus
    original_filename: str
    mime_type: str
    size_bytes: int
    page_count: int | None = None
    sha256: str
    metadata: dict[str, Any] = {}
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None


class DocumentSummary(APIModel):
    id: UUID
    type: DocumentType
    status: DocumentStatus
    original_filename: str
    mime_type: str
    size_bytes: int
    page_count: int | None = None
    sha256: str
    created_at: datetime


class DownloadUrlOut(APIModel):
    url: str
    expires_in: int
