"""Admin dashboard/audit DTOs."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import UserRole
from app.schemas.base import APIModel


class TierCount(BaseModel):
    tier: int
    count: int


class DashboardMetrics(BaseModel):
    workers: int
    active_journeys: int
    verifications_this_week: int
    high_risk_verifications: int
    open_cases: int
    open_cases_by_tier: list[TierCount]
    overdue_checkins: int
    agency_alerts: int


class RecentActivity(BaseModel):
    kind: str
    id: UUID
    title: str
    status: str
    created_at: datetime


class DashboardOut(BaseModel):
    metrics: DashboardMetrics
    recent_activity: list[RecentActivity] = Field(default_factory=list)


class AuditLogOut(APIModel):
    id: UUID
    actor_id: UUID | None = None
    actor_role: UserRole | None = None
    action: str
    entity_type: str | None = None
    entity_id: UUID | None = None
    ip_address: str | None = None
    user_agent: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
