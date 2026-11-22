"""Verification DTOs."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import RiskLevel, VerificationStatus
from app.schemas.base import APIModel


class VerificationCreate(BaseModel):
    agency_id: UUID | None = None
    agency_name_input: str | None = Field(default=None, max_length=300)
    job_title: str | None = Field(default=None, max_length=300)
    employer_name: str | None = Field(default=None, max_length=300)
    destination_country: str | None = Field(default=None, max_length=100)
    offered_salary: float | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, max_length=8)
    document_ids: list[UUID] = Field(default_factory=list)


class VerificationOut(APIModel):
    id: UUID
    user_id: UUID
    agency_id: UUID | None = None
    agency_name: str | None = None
    agency_registration_no: str | None = None
    agency_name_input: str | None = None
    job_title: str | None = None
    employer_name: str | None = None
    destination_country: str | None = None
    offered_salary: float | None = None
    currency: str | None = None
    status: VerificationStatus
    risk_level: RiskLevel | None = None
    risk_score: int | None = None
    findings: list[dict[str, Any]] = Field(default_factory=list)
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    engine_version: str | None = None
    analysis_run_id: str | None = None
    failure_code: str | None = None
    failure_message: str | None = None
    reviewed_by: UUID | None = None
    reviewed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None


class VerificationReview(BaseModel):
    status: VerificationStatus
    risk_level: RiskLevel | None = None
    risk_score: int | None = Field(default=None, ge=0, le=100)
    findings: list[dict[str, Any]] | None = None
    note: str | None = Field(default=None, max_length=2000)
