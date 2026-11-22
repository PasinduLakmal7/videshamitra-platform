"""Admin dashboard, AI trace proxy and audit queries."""

from __future__ import annotations

from uuid import UUID

import asyncpg

from app.core.exceptions import Forbidden
from app.core.permissions import is_admin, is_staff
from app.integrations.ai_client import AIClient
from app.models.entities import CurrentUser
from app.repositories.complaint_repository import ComplaintRepository
from app.schemas.admin import (
    DashboardMetrics,
    DashboardOut,
    RecentActivity,
    TierCount,
)
from app.services.audit_service import AuditService


class AdminService:
    def __init__(
        self,
        complaints: ComplaintRepository | None = None,
        audit: AuditService | None = None,
        ai_client: AIClient | None = None,
    ) -> None:
        self.complaints = complaints or ComplaintRepository()
        self.audit = audit or AuditService()
        self.ai_client = ai_client

    async def dashboard(self, conn: asyncpg.Connection, *, actor: CurrentUser) -> DashboardOut:
        if not is_staff(actor):
            raise Forbidden("Staff access required")
        counts = await conn.fetchrow(
            """
            select
                (select count(*) from core.users
                 where role = 'worker' and is_active) as workers,
                (select count(*) from core.migration_journeys
                 where stage <> 'returned') as active_journeys,
                (select count(*) from core.verifications
                 where created_at >= date_trunc('week', now())) as verifications_this_week,
                (select count(*) from core.verifications
                 where risk_level in ('high', 'critical')
                   and created_at >= now() - interval '30 days') as high_risk_verifications,
                (select count(*) from core.checkins
                 where due_at < now() and status in ('scheduled', 'sent')) as overdue_checkins,
                (select count(*) from core.agencies
                 where license_status in ('suspended', 'expired', 'cancelled')) as agency_alerts
            """
        )
        open_cases = await self.complaints.count_open(conn)
        tiers = await self.complaints.open_by_tier(conn)

        recent_rows = await conn.fetch(
            """
            (
                select 'verification'::text as kind, id,
                       coalesce(job_title, 'Verification')::text as title,
                       status::text as status, created_at
                from core.verifications
                order by created_at desc
                limit 5
            )
            union all
            (
                select 'case'::text as kind, id, title, status::text as status, created_at
                from core.complaints
                order by created_at desc
                limit 5
            )
            order by created_at desc
            limit 10
            """
        )
        metrics = DashboardMetrics(
            workers=int(counts["workers"]),
            active_journeys=int(counts["active_journeys"]),
            verifications_this_week=int(counts["verifications_this_week"]),
            high_risk_verifications=int(counts["high_risk_verifications"]),
            open_cases=open_cases,
            open_cases_by_tier=[
                TierCount(tier=int(row["triage_tier"]), count=int(row["count"])) for row in tiers
            ],
            overdue_checkins=int(counts["overdue_checkins"]),
            agency_alerts=int(counts["agency_alerts"]),
        )
        return DashboardOut(
            metrics=metrics,
            recent_activity=[
                RecentActivity(
                    kind=row["kind"],
                    id=row["id"],
                    title=row["title"],
                    status=row["status"],
                    created_at=row["created_at"],
                )
                for row in recent_rows
            ],
        )

    async def trace(self, *, actor: CurrentUser, verification_id: UUID) -> dict:
        if not is_staff(actor):
            raise Forbidden("Staff access required")
        if self.ai_client is None:
            from app.core.config import settings

            self.ai_client = AIClient(settings.AI_SERVICE_URL)
        return await self.ai_client.get_trace(str(verification_id))

    async def audit_logs(
        self,
        conn: asyncpg.Connection,
        *,
        actor: CurrentUser,
        actor_id: UUID | None,
        action: str | None,
        entity_type: str | None,
        entity_id: UUID | None,
        page_size: int,
        offset: int,
    ):
        if not is_admin(actor):
            raise Forbidden("Admin access required")
        return await self.audit.list_logs(
            conn,
            actor_id=actor_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            page_size=page_size,
            offset=offset,
        )
