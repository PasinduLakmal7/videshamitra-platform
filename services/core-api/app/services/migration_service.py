"""Journeys, consent, Day 7/30/90 check-ins, responses and escalation."""

from __future__ import annotations

import json
import logging
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from uuid import UUID

import asyncpg

from app.core.config import settings
from app.core.exceptions import BadRequest, Conflict, Forbidden, NotFound
from app.core.permissions import is_staff
from app.models.entities import CurrentUser, RequestInfo
from app.models.enums import (
    CheckinStatus,
    ConsentType,
    JourneyStage,
    NotificationType,
    RiskLevel,
)
from app.repositories.migration_repository import MigrationRepository
from app.repositories.user_repository import UserRepository
from app.schemas.migration import (
    CheckinCreate,
    CheckinEscalate,
    CheckinRespond,
    CheckinUpdate,
    JourneyConsent,
    JourneyCreate,
    JourneyUpdate,
)
from app.services.audit_service import AuditService
from app.services.complaint_service import ComplaintService
from app.services.notification_service import NotificationService

logger = logging.getLogger(__name__)

CHECKIN_OFFSETS = (7, 30, 90)
_STAGE_TRANSITIONS = {
    JourneyStage.PRE_DEPARTURE: {JourneyStage.EMPLOYED_ABROAD},
    JourneyStage.EMPLOYED_ABROAD: {JourneyStage.RETURNED},
    JourneyStage.RETURNED: set(),
}


def _checkin_datetime(departure: date | None, offset_days: int) -> datetime:
    base = departure or datetime.now(UTC).date()
    return datetime.combine(base + timedelta(days=offset_days), time(9, 0), tzinfo=UTC)


def infer_risk(response: dict[str, Any]) -> RiskLevel | None:
    explicit = response.get("risk_level") if isinstance(response, dict) else None
    if explicit in {item.value for item in RiskLevel}:
        return RiskLevel(explicit)
    for key in ("is_safe", "safe", "feeling_safe"):
        if response.get(key) is False:
            return RiskLevel.HIGH
    text = json.dumps(response, default=str).lower()
    danger_terms = (
        "unsafe",
        "abuse",
        "threat",
        "confiscat",
        "passport kept",
        "not paid",
        "unpaid",
        "harass",
        "locked in",
    )
    if any(term in text for term in danger_terms):
        return RiskLevel.HIGH
    return None


class MigrationService:
    def __init__(
        self,
        repo: MigrationRepository | None = None,
        users: UserRepository | None = None,
        notifications: NotificationService | None = None,
        complaints: ComplaintService | None = None,
        audit: AuditService | None = None,
    ) -> None:
        self.repo = repo or MigrationRepository()
        self.users = users or UserRepository()
        self.notifications = notifications or NotificationService()
        self.complaints = complaints or ComplaintService()
        self.audit = audit or AuditService()

    async def create_journey(
        self,
        conn: asyncpg.Connection,
        *,
        actor: CurrentUser,
        payload: JourneyCreate,
        request: RequestInfo,
    ) -> asyncpg.Record:
        existing = await self.repo.active_journey_for_user(conn, actor.id)
        if existing is not None:
            raise Conflict(
                "An active journey already exists for this user",
                code="active_journey_exists",
                details={"journey_id": str(existing["id"])},
            )
        try:
            row = await self.repo.create_journey(
                conn,
                user_id=actor.id,
                agency_id=payload.agency_id,
                destination_country=payload.destination_country,
                employer_name=payload.employer_name,
                job_title=payload.job_title,
                departure_date=payload.departure_date,
                return_date=payload.return_date,
            )
        except asyncpg.UniqueViolationError as exc:
            raise Conflict(
                "An active journey already exists for this user",
                code="active_journey_exists",
            ) from exc
        await self.audit.record(
            conn,
            actor=actor,
            action="journey.created",
            entity_type="migration_journey",
            entity_id=row["id"],
            request=request,
        )
        return row

    async def get_journey(
        self, conn: asyncpg.Connection, *, actor: CurrentUser, journey_id: UUID
    ) -> asyncpg.Record:
        row = await self.repo.get_journey(conn, journey_id)
        if row is None:
            raise NotFound("Journey not found")
        if row["user_id"] != actor.id and not is_staff(actor):
            raise Forbidden("You do not have access to this journey")
        return row

    async def list_journeys(
        self,
        conn: asyncpg.Connection,
        *,
        actor: CurrentUser,
        user_id: UUID | None,
        stage: str | None,
        page_size: int,
        offset: int,
        order_by: str,
    ):
        effective_user = user_id if is_staff(actor) else actor.id
        return await self.repo.list_journeys(
            conn,
            user_id=effective_user,
            stage=stage,
            page_size=page_size,
            offset=offset,
            order_by=order_by,
        )

    async def update_journey(
        self,
        conn: asyncpg.Connection,
        *,
        actor: CurrentUser,
        journey_id: UUID,
        payload: JourneyUpdate,
        request: RequestInfo,
    ) -> asyncpg.Record:
        await self.get_journey(conn, actor=actor, journey_id=journey_id)
        fields = payload.model_dump(exclude_unset=True)
        row = await self.repo.update_journey(conn, journey_id, fields)
        if row is None:
            raise NotFound("Journey not found")
        await self.audit.record(
            conn,
            actor=actor,
            action="journey.updated",
            entity_type="migration_journey",
            entity_id=journey_id,
            request=request,
            metadata={"fields": sorted(fields)},
        )
        return row

    async def set_consent(
        self,
        conn: asyncpg.Connection,
        *,
        actor: CurrentUser,
        journey_id: UUID,
        payload: JourneyConsent,
        request: RequestInfo,
    ) -> asyncpg.Record:
        journey = await self.repo.get_journey(conn, journey_id)
        if journey is None:
            raise NotFound("Journey not found")
        if journey["user_id"] != actor.id:
            raise Forbidden("Only the worker can change check-in consent")

        async with conn.transaction():
            row = await self.repo.set_consent(conn, journey_id, payload.granted)
            if row is None:
                raise NotFound("Journey not found")
            await self.users.create_consent(
                conn,
                user_id=actor.id,
                consent_type=ConsentType.CHECKINS,
                granted=payload.granted,
                version=payload.version,
                ip_address=None,
                user_agent=None,
            )
            if payload.granted:
                for offset in CHECKIN_OFFSETS:
                    due_at = _checkin_datetime(journey["departure_date"], offset)
                    await self.repo.create_checkin(
                        conn,
                        journey_id=journey_id,
                        user_id=actor.id,
                        due_at=due_at,
                    )
            await self.repo.refresh_next_checkin(conn, journey_id)
            await self.audit.record(
                conn,
                actor=actor,
                action="journey.consent_updated",
                entity_type="migration_journey",
                entity_id=journey_id,
                request=request,
                metadata={"granted": payload.granted},
            )
        refreshed = await self.repo.get_journey(conn, journey_id)
        assert refreshed is not None
        return refreshed

    async def update_stage(
        self,
        conn: asyncpg.Connection,
        *,
        actor: CurrentUser,
        journey_id: UUID,
        stage: JourneyStage,
        request: RequestInfo,
    ) -> asyncpg.Record:
        if not is_staff(actor):
            raise Forbidden("Staff access required")
        journey = await self.repo.get_journey(conn, journey_id)
        if journey is None:
            raise NotFound("Journey not found")
        current = JourneyStage(journey["stage"])
        if stage != current and stage not in _STAGE_TRANSITIONS[current]:
            raise Conflict(
                f"Cannot move journey from {current.value} to {stage.value}",
                code="invalid_transition",
            )
        row = await self.repo.set_stage(conn, journey_id, stage.value)
        if row is None:
            raise NotFound("Journey not found")
        await self.audit.record(
            conn,
            actor=actor,
            action="journey.stage_changed",
            entity_type="migration_journey",
            entity_id=journey_id,
            request=request,
            metadata={"stage": stage.value},
        )
        return row

    # --- check-ins ------------------------------------------------------
    async def get_checkin(
        self, conn: asyncpg.Connection, *, actor: CurrentUser, checkin_id: UUID
    ) -> asyncpg.Record:
        row = await self.repo.get_checkin(conn, checkin_id)
        if row is None:
            raise NotFound("Check-in not found")
        if row["user_id"] != actor.id and not is_staff(actor):
            raise Forbidden("You do not have access to this check-in")
        return row

    async def list_checkins(
        self,
        conn: asyncpg.Connection,
        *,
        actor: CurrentUser,
        user_id: UUID | None,
        journey_id: UUID | None,
        status: str | None,
        overdue_only: bool,
        page_size: int,
        offset: int,
        order_by: str,
    ):
        effective_user = user_id if is_staff(actor) else actor.id
        return await self.repo.list_checkins(
            conn,
            user_id=effective_user,
            journey_id=journey_id,
            status=status,
            overdue_only=overdue_only,
            page_size=page_size,
            offset=offset,
            order_by=order_by,
        )

    async def respond(
        self,
        conn: asyncpg.Connection,
        *,
        actor: CurrentUser,
        checkin_id: UUID,
        payload: CheckinRespond,
        request: RequestInfo,
    ) -> asyncpg.Record:
        checkin = await self.repo.get_checkin(conn, checkin_id)
        if checkin is None:
            raise NotFound("Check-in not found")
        if checkin["user_id"] != actor.id:
            raise Forbidden("Only the worker can respond to this check-in")

        risk = payload.risk_level or infer_risk(payload.response)
        async with conn.transaction():
            row = await self.repo.respond(
                conn,
                checkin_id=checkin_id,
                user_id=actor.id,
                response=payload.response,
                risk_level=risk.value if risk else None,
            )
            if row is None:
                current = await self.repo.get_checkin(conn, checkin_id)
                if current is not None and current["status"] == CheckinStatus.COMPLETED:
                    return current
                raise Conflict(
                    "This check-in cannot be answered",
                    code="checkin_not_open",
                )
            if risk in (RiskLevel.HIGH, RiskLevel.CRITICAL):
                await self.repo.mark_escalated(conn, checkin_id)
                await self.complaints.create_or_escalate_from_checkin(
                    conn,
                    checkin=checkin,
                    reason=f"High-risk check-in response ({risk.value}).",
                    triage_tier=2,
                    risk_level=risk,
                )
                await self.notifications.notify_staff(
                    conn,
                    title="High-risk check-in",
                    body="A worker reported a high-risk situation.",
                    data={"checkin_id": str(checkin_id)},
                    deep_link="videshamitra://admin/cases",
                )
            await self.repo.refresh_next_checkin(conn, row["journey_id"])
            await self.audit.record(
                conn,
                actor=actor,
                action="checkin.responded",
                entity_type="checkin",
                entity_id=checkin_id,
                request=request,
                metadata={"risk_level": risk.value if risk else None},
            )
        refreshed = await self.repo.get_checkin(conn, checkin_id)
        assert refreshed is not None
        return refreshed

    async def escalate_checkin(
        self,
        conn: asyncpg.Connection,
        *,
        actor: CurrentUser,
        checkin_id: UUID,
        payload: CheckinEscalate,
        request: RequestInfo,
    ) -> asyncpg.Record:
        if not is_staff(actor):
            raise Forbidden("Staff access required")
        checkin = await self.repo.get_checkin(conn, checkin_id)
        if checkin is None:
            raise NotFound("Check-in not found")
        if checkin["status"] in (CheckinStatus.ESCALATED, CheckinStatus.COMPLETED):
            raise Conflict("Check-in is already closed", code="invalid_transition")
        async with conn.transaction():
            row = await self.repo.mark_escalated(conn, checkin_id)
            await self.complaints.create_or_escalate_from_checkin(
                conn,
                checkin=checkin,
                reason=payload.reason or "Caseworker escalated this check-in.",
                triage_tier=payload.triage_tier,
            )
            await self.audit.record(
                conn,
                actor=actor,
                action="checkin.escalated",
                entity_type="checkin",
                entity_id=checkin_id,
                request=request,
                metadata={"tier": payload.triage_tier},
            )
        assert row is not None
        return row

    async def schedule_checkin(
        self,
        conn: asyncpg.Connection,
        *,
        actor: CurrentUser,
        payload: CheckinCreate,
        request: RequestInfo,
    ) -> asyncpg.Record:
        if not is_staff(actor):
            raise Forbidden("Staff access required")
        journey = await self.repo.get_journey(conn, payload.journey_id)
        if journey is None:
            raise NotFound("Journey not found")
        if payload.due_at.tzinfo is None:
            raise BadRequest("due_at must include a timezone")
        row = await self.repo.create_checkin(
            conn,
            journey_id=payload.journey_id,
            user_id=journey["user_id"],
            due_at=payload.due_at,
            channel=payload.channel.value,
        )
        if row is None:
            raise Conflict("A check-in already exists at that time", code="duplicate_checkin")
        await self.repo.refresh_next_checkin(conn, payload.journey_id)
        await self.audit.record(
            conn,
            actor=actor,
            action="checkin.scheduled",
            entity_type="checkin",
            entity_id=row["id"],
            request=request,
        )
        return row

    async def update_checkin(
        self,
        conn: asyncpg.Connection,
        *,
        actor: CurrentUser,
        checkin_id: UUID,
        payload: CheckinUpdate,
        request: RequestInfo,
    ) -> asyncpg.Record:
        if not is_staff(actor):
            raise Forbidden("Staff access required")
        checkin = await self.repo.get_checkin(conn, checkin_id)
        if checkin is None:
            raise NotFound("Check-in not found")
        fields = payload.model_dump(exclude_unset=True, exclude_none=True)
        if "channel" in fields:
            fields["channel"] = (
                fields["channel"].value
                if hasattr(fields["channel"], "value")
                else fields["channel"]
            )
        if "status" in fields:
            fields["status"] = (
                fields["status"].value if hasattr(fields["status"], "value") else fields["status"]
            )
        row = await self.repo.update_checkin(conn, checkin_id, fields)
        if row is None:
            raise NotFound("Check-in not found")
        await self.repo.refresh_next_checkin(conn, checkin["journey_id"])
        await self.audit.record(
            conn,
            actor=actor,
            action="checkin.updated",
            entity_type="checkin",
            entity_id=checkin_id,
            request=request,
            metadata={"fields": sorted(fields)},
        )
        return row

    async def overdue(
        self,
        conn: asyncpg.Connection,
        *,
        actor: CurrentUser,
        page_size: int,
        offset: int,
        order_by: str,
    ):
        if not is_staff(actor):
            raise Forbidden("Staff access required")
        return await self.repo.list_checkins(
            conn,
            user_id=None,
            journey_id=None,
            status=None,
            overdue_only=True,
            page_size=page_size,
            offset=offset,
            order_by=order_by,
        )

    # --- workers --------------------------------------------------------

    async def send_due_checkins(self, conn: asyncpg.Connection) -> int:
        sent = 0
        async with conn.transaction():
            due = await self.repo.due_checkins(conn)
            for checkin in due:
                async with conn.transaction():
                    row = await self.repo.mark_sent(conn, checkin["id"])
                    if row is None:
                        continue
                    await self.notifications.request_delivery(
                        conn,
                        user_id=checkin["user_id"],
                        notification_type=NotificationType.CHECKIN_DUE,
                        title="Safety check-in",
                        body="How are you doing? Tap to complete your check-in.",
                        data={
                            "checkin_id": str(checkin["id"]),
                            "journey_id": str(checkin["journey_id"]),
                        },
                        deep_link=f"videshamitra://checkins/{checkin['id']}",
                        channels=["push", "whatsapp", "in_app"],
                    )
                    await self.audit.record(
                        conn,
                        actor=None,
                        action="checkin.sent",
                        entity_type="checkin",
                        entity_id=checkin["id"],
                        metadata={"journey_id": str(checkin["journey_id"])},
                        actor_service="core-api-worker",
                    )
                    sent += 1
        if sent:
            logger.info("checkins_sent", extra={"count": sent})
        return sent

    async def escalate_missed(self, conn: asyncpg.Connection) -> int:
        escalated = 0
        async with conn.transaction():
            missed = await self.repo.missed_checkins(conn, grace_hours=settings.CHECKIN_GRACE_HOURS)
            for checkin in missed:
                async with conn.transaction():
                    row = await self.repo.mark_missed(conn, checkin["id"])
                    if row is None:
                        continue
                    reason = "A scheduled safety check-in was missed after the grace period."
                    await self.complaints.create_or_escalate_from_checkin(
                        conn,
                        checkin=checkin,
                        reason=reason,
                        triage_tier=2,
                    )
                    await self.notifications.request_delivery(
                        conn,
                        user_id=checkin["user_id"],
                        notification_type=NotificationType.CHECKIN_MISSED,
                        title="We missed you",
                        body=(
                            "You missed a safety check-in. Please respond or contact a caseworker."
                        ),
                        data={"checkin_id": str(checkin["id"])},
                        deep_link=f"videshamitra://checkins/{checkin['id']}",
                        channels=["push", "whatsapp", "sms"],
                    )
                    await self.audit.record(
                        conn,
                        actor=None,
                        action="checkin.missed_escalated",
                        entity_type="checkin",
                        entity_id=checkin["id"],
                        metadata={"journey_id": str(checkin["journey_id"])},
                        actor_service="core-api-worker",
                    )
                    escalated += 1
        if escalated:
            logger.info("checkins_missed_escalated", extra={"count": escalated})
        return escalated
