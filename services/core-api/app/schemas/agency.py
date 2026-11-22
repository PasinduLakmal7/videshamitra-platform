"""Agency DTOs."""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import AgencyLicenseStatus
from app.schemas.base import APIModel


class AgencyOut(APIModel):
    id: UUID
    registration_no: str
    name: str
    normalized_name: str | None = None
    license_no: str | None = None
    license_status: AgencyLicenseStatus
    license_expires_on: date | None = None
    address: str | None = None
    district: str | None = None
    phone: str | None = None
    email: str | None = None
    latest_snapshot_id: UUID | None = None
    created_at: datetime
    updated_at: datetime


class AgencyCreate(BaseModel):
    registration_no: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=300)
    license_no: str | None = None
    license_status: AgencyLicenseStatus = AgencyLicenseStatus.UNKNOWN
    license_expires_on: date | None = None
    address: str | None = None
    district: str | None = None
    phone: str | None = None
    email: str | None = None


class AgencyUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=300)
    license_no: str | None = None
    license_status: AgencyLicenseStatus | None = None
    license_expires_on: date | None = None
    address: str | None = None
    district: str | None = None
    phone: str | None = None
    email: str | None = None


class LicenseHistoryOut(APIModel):
    id: UUID
    agency_id: UUID
    snapshot_id: UUID | None = None
    license_no: str | None = None
    status: AgencyLicenseStatus
    issued_on: date | None = None
    expires_on: date | None = None
    job_categories: list[str] | None = None
    raw_data: dict | None = None
    created_at: datetime


class AgencyImportRequest(BaseModel):
    """Imports from the configured SLBFE_SOURCE_URL; ad-hoc sources use the CLI."""

    snapshot_date: date | None = None
    dry_run: bool = False


class SnapshotOut(APIModel):
    id: UUID
    snapshot_date: date
    source_url: str | None = None
    checksum: str
    record_count: int
    imported_by: UUID | None = None
    imported_at: datetime


class ImportResult(BaseModel):
    snapshot_id: str | None = None
    snapshot_date: date
    checksum: str
    parsed: int
    imported: int
    errors: list[str] = Field(default_factory=list)
    duplicate_snapshot: bool = False
    dry_run: bool = False
