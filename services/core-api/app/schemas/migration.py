"""Journey and check-in DTOs."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import CheckinStatus, JourneyStage, NotificationChannel, RiskLevel
from app.schemas.base import APIModel


class JourneyCreate(BaseModel):
    agency_id: UUID | None = None
    destination_country: str | None = Field(default=None, max_length=100)
    employer_name: str | None = Field(default=None, max_length=300)
    job_title: str | None = Field(default=None, max_length=300)
    departure_date: date | None = None
    return_date: date | None = None


class JourneyUpdate(BaseModel):
    agency_id: UUID | None = None
    destination_country: str | None = Field(default=None, max_length=100)
    employer_name: str | None = Field(default=None, max_length=300)
    job_title: str | None = Field(default=None, max_length=300)
    departure_date: date | None = None
    return_date: date | None = None


class JourneyOut(APIModel):
    id: UUID
    user_id: UUID
    agency_id: UUID | None = None
    agency_name: str | None = None
    destination_country: str | None = None
    employer_name: str | None = None
    job_title: str | None = None
    departure_date: date | None = None
    return_date: date | None = None
    stage: JourneyStage
    consent_checkins: bool
    consent_at: datetime | None = None
    next_checkin_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class JourneyConsent(BaseModel):
    granted: bool
    version: str = Field(default="1", max_length=32)


class JourneyStageUpdate(BaseModel):
    stage: JourneyStage


class CheckinOut(APIModel):
    id: UUID
    journey_id: UUID
    user_id: UUID
    due_at: datetime
    channel: NotificationChannel
    status: CheckinStatus
    sent_at: datetime | None = None
    completed_at: datetime | None = None
    response: dict[str, Any] | None = None
    risk_level: RiskLevel | None = None
    created_at: datetime
    updated_at: datetime


class CheckinCreate(BaseModel):
    journey_id: UUID
    due_at: datetime
    channel: NotificationChannel = NotificationChannel.IN_APP


class CheckinUpdate(BaseModel):
    due_at: datetime | None = None
    channel: NotificationChannel | None = None
    status: CheckinStatus | None = None


class CheckinRespond(BaseModel):
    response: dict[str, Any] = Field(default_factory=dict)
    risk_level: RiskLevel | None = None


class CheckinEscalate(BaseModel):
    reason: str | None = Field(default=None, max_length=2000)
    triage_tier: int = Field(default=2, ge=1, le=3)
