"""Complaint/case DTOs."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import ComplaintStatus
from app.schemas.base import APIModel
from app.schemas.document import DocumentSummary
from app.schemas.migration import CheckinOut, JourneyOut
from app.schemas.user import UserOut
from app.schemas.verification import VerificationOut


class ComplaintCreate(BaseModel):
    title: str = Field(min_length=3, max_length=300)
    description: str | None = Field(default=None, max_length=10000)
    journey_id: UUID | None = None
    verification_id: UUID | None = None
    agency_id: UUID | None = None
    checkin_id: UUID | None = None
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    draft_text: str | None = Field(default=None, max_length=20000)
    document_ids: list[UUID] = Field(default_factory=list)


class ComplaintUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=300)
    description: str | None = Field(default=None, max_length=10000)
    evidence: list[dict[str, Any]] | None = None
    draft_text: str | None = Field(default=None, max_length=20000)


class ComplaintOut(APIModel):
    id: UUID
    user_id: UUID
    journey_id: UUID | None = None
    verification_id: UUID | None = None
    agency_id: UUID | None = None
    checkin_id: UUID | None = None
    title: str
    description: str | None = None
    status: ComplaintStatus
    triage_tier: int
    assigned_to: UUID | None = None
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    draft_text: str | None = None
    submitted_at: datetime | None = None
    resolved_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    worker_name: str | None = None
    worker_phone: str | None = None
    agency_name: str | None = None


class ComplaintAttachDocuments(BaseModel):
    document_ids: list[UUID] = Field(min_length=1)


class CaseUpdate(BaseModel):
    status: ComplaintStatus | None = None
    triage_tier: int | None = Field(default=None, ge=1, le=3)
    assigned_to: UUID | None = None
    note: str | None = Field(default=None, max_length=5000)


class CaseEscalate(BaseModel):
    reason: str | None = Field(default=None, max_length=5000)
    triage_tier: int = Field(default=2, ge=1, le=3)


class CaseNoteCreate(BaseModel):
    body: str = Field(min_length=1, max_length=5000)
    is_internal: bool = True


class CaseNoteOut(APIModel):
    id: UUID
    complaint_id: UUID
    author_id: UUID | None = None
    author_name: str | None = None
    body: str
    is_internal: bool
    created_at: datetime


class CaseDetail(BaseModel):
    case: ComplaintOut
    worker: UserOut | None = None
    journey: JourneyOut | None = None
    verification: VerificationOut | None = None
    checkin: CheckinOut | None = None
    documents: list[DocumentSummary] = Field(default_factory=list)
    notes: list[CaseNoteOut] = Field(default_factory=list)
