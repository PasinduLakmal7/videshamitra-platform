"""Complaints, evidence, case management, notes and escalation."""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

import asyncpg

from app.core.exceptions import BadRequest, Conflict, Forbidden, NotFound
from app.core.permissions import is_staff
from app.models.entities import CurrentUser, RequestInfo
from app.models.enums import (
    COMPLAINT_TRANSITIONS,
    ComplaintStatus,
    NotificationType,
    RiskLevel,
    can_transition,
)
from app.repositories.agency_repository import AgencyRepository
from app.repositories.complaint_repository import ComplaintRepository
from app.repositories.document_repository import DocumentRepository
from app.repositories.migration_repository import MigrationRepository
from app.repositories.user_repository import UserRepository
from app.repositories.verification_repository import VerificationRepository
from app.schemas.complaint import (
    CaseEscalate,
    CaseNoteCreate,
    CaseUpdate,
    ComplaintCreate,
    ComplaintUpdate,
)
from app.services.audit_service import AuditService
from app.services.notification_service import NotificationService

logger = logging.getLogger(__name__)


class ComplaintService:
    def __init__(
        self,
        repo: ComplaintRepository | None = None,
        notifications: NotificationService | None = None,
        audit: AuditService | None = None,
        users: UserRepository | None = None,
    ) -> None:
        self.repo = repo or ComplaintRepository()
        self.notifications = notifications or NotificationService()
        self.audit = audit or AuditService()
        self.users = users or UserRepository()
        self.journeys = MigrationRepository()
        self.verifications = VerificationRepository()
        self.documents = DocumentRepository()
        self.agencies = AgencyRepository()

    async def _assert_owner(self, row: Any, actor: CurrentUser, what: str) -> None:
        if row["user_id"] != actor.id:
            raise Forbidden(f"You do not have access to this {what}")

    async def create(
        self,
        conn: asyncpg.Connection,
        *,
        actor: CurrentUser,
        payload: ComplaintCreate,
        request: RequestInfo,
    ) -> asyncpg.Record:
        if payload.journey_id:
            journey = await self.journeys.get_journey(conn, payload.journey_id)
            if journey is None:
                raise BadRequest("Journey not found", code="journey_not_found")
            await self._assert_owner(journey, actor, "journey")
        if payload.verification_id:
            verification = await self.verifications.get(conn, payload.verification_id)
            if verification is None:
                raise BadRequest("Verification not found", code="verification_not_found")
            await self._assert_owner(verification, actor, "verification")
        if payload.checkin_id:
            checkin = await self.journeys.get_checkin(conn, payload.checkin_id)
            if checkin is None:
                raise BadRequest("Check-in not found", code="checkin_not_found")
            await self._assert_owner(checkin, actor, "check-in")
        if payload.agency_id:
            agency = await self.agencies.get(conn, payload.agency_id)
            if agency is None:
                raise BadRequest("Agency not found", code="agency_not_found")
        for document_id in payload.document_ids:
            document = await self.documents.get(conn, document_id)
            if document is None or document["user_id"] != actor.id:
                raise BadRequest(
                    "One or more evidence documents were not found",
                    code="document_not_found",
                    details={"document_id": str(document_id)},
                )

        async with conn.transaction():
            row = await self.repo.create(
                conn,
                user_id=actor.id,
                title=payload.title,
                description=payload.description,
                journey_id=payload.journey_id,
                verification_id=payload.verification_id,
                agency_id=payload.agency_id,
                checkin_id=payload.checkin_id,
                evidence=payload.evidence,
                draft_text=payload.draft_text,
                document_ids=payload.document_ids,
            )
            await self.audit.record(
                conn,
                actor=actor,
                action="complaint.created",
                entity_type="complaint",
                entity_id=row["id"],
                request=request,
                metadata={"documents": len(payload.document_ids)},
            )
        return row

    async def list_complaints(
        self,
        conn: asyncpg.Connection,
        *,
        actor: CurrentUser,
        user_id: UUID | None,
        status: str | None,
        triage_tier: int | None,
        assigned_to: UUID | None,
        q: str | None,
        page_size: int,
        offset: int,
        order_by: str,
    ):
        effective_user = user_id if is_staff(actor) else actor.id
        return await self.repo.list_complaints(
            conn,
            user_id=effective_user,
            status=status,
            triage_tier=triage_tier,
            assigned_to=assigned_to,
            q=q,
            page_size=page_size,
            offset=offset,
            order_by=order_by,
        )

    async def get_complaint(
        self, conn: asyncpg.Connection, *, actor: CurrentUser, complaint_id: UUID
    ) -> asyncpg.Record:
        row = await self.repo.get(conn, complaint_id)
        if row is None:
            raise NotFound("Complaint not found")
        if row["user_id"] != actor.id and not is_staff(actor):
            raise Forbidden("You do not have access to this complaint")
        return row

    async def detail(
        self, conn: asyncpg.Connection, *, actor: CurrentUser, complaint_id: UUID
    ) -> dict[str, Any]:
        complaint = await self.get_complaint(conn, actor=actor, complaint_id=complaint_id)
        worker = await self.users.get_by_id(conn, complaint["user_id"])
        journey = (
            await self.journeys.get_journey(conn, complaint["journey_id"])
            if complaint["journey_id"]
            else None
        )
        verification = (
            await self.verifications.get(conn, complaint["verification_id"])
            if complaint["verification_id"]
            else None
        )
        checkin = (
            await self.journeys.get_checkin(conn, complaint["checkin_id"])
            if complaint["checkin_id"]
            else None
        )
        documents = await self.repo.list_documents(conn, complaint_id)
        notes = await self.repo.list_notes(conn, complaint_id) if is_staff(actor) else []
        return {
            "case": complaint,
            "worker": worker,
            "journey": journey,
            "verification": verification,
            "checkin": checkin,
            "documents": documents,
            "notes": notes,
        }

    async def update(
        self,
        conn: asyncpg.Connection,
        *,
        actor: CurrentUser,
        complaint_id: UUID,
        payload: ComplaintUpdate,
        request: RequestInfo,
    ) -> asyncpg.Record:
        complaint = await self.get_complaint(conn, actor=actor, complaint_id=complaint_id)
        fields = payload.model_dump(exclude_unset=True)
        if is_staff(actor) and complaint["user_id"] != actor.id:
            row = await self.repo.update_case(conn, complaint_id, fields)
        else:
            if complaint["status"] != ComplaintStatus.DRAFT:
                raise Conflict(
                    "Only draft complaints can be edited by the worker",
                    code="complaint_not_draft",
                )
            row = await self.repo.update_draft(
                conn, complaint_id=complaint_id, user_id=actor.id, fields=fields
            )
        if row is None:
            raise NotFound("Complaint not found")
        await self.audit.record(
            conn,
            actor=actor,
            action="complaint.updated",
            entity_type="complaint",
            entity_id=complaint_id,
            request=request,
            metadata={"fields": sorted(fields)},
        )
        return row

    async def submit(
        self,
        conn: asyncpg.Connection,
        *,
        actor: CurrentUser,
        complaint_id: UUID,
        request: RequestInfo,
    ) -> asyncpg.Record:
        complaint = await self.repo.get(conn, complaint_id)
        if complaint is None:
            raise NotFound("Complaint not found")
        if complaint["user_id"] != actor.id:
            raise Forbidden("Only the owner can submit a complaint")
        async with conn.transaction():
            row = await self.repo.submit(conn, complaint_id=complaint_id, user_id=actor.id)
            if row is None:
                raise Conflict(
                    "Only draft complaints can be submitted",
                    code="invalid_transition",
                )
            await self.notifications.notify_staff(
                conn,
                title="New complaint submitted",
                body=f"{complaint['title']}",
                data={"complaint_id": str(complaint_id)},
                deep_link=f"videshamitra://admin/cases/{complaint_id}",
            )
            await self.audit.record(
                conn,
                actor=actor,
                action="complaint.submitted",
                entity_type="complaint",
                entity_id=complaint_id,
                request=request,
            )
        return row

    async def attach_documents(
        self,
        conn: asyncpg.Connection,
        *,
        actor: CurrentUser,
        complaint_id: UUID,
        document_ids: list[UUID],
        request: RequestInfo,
    ) -> asyncpg.Record:
        complaint = await self.repo.get(conn, complaint_id)
        if complaint is None:
            raise NotFound("Complaint not found")
        if complaint["user_id"] != actor.id:
            raise Forbidden("Only the owner can attach evidence")
        if complaint["status"] in (ComplaintStatus.CLOSED, ComplaintStatus.RESOLVED):
            raise Conflict("This complaint is closed", code="complaint_closed")
        attached = await self.repo.add_documents(
            conn, complaint_id=complaint_id, user_id=actor.id, document_ids=document_ids
        )
        if attached == 0:
            raise BadRequest(
                "No valid documents were attached",
                code="documents_not_found",
            )
        await self.audit.record(
            conn,
            actor=actor,
            action="complaint.documents_attached",
            entity_type="complaint",
            entity_id=complaint_id,
            request=request,
            metadata={"count": attached},
        )
        refreshed = await self.repo.get(conn, complaint_id)
        assert refreshed is not None
        return refreshed

    async def list_cases(
        self,
        conn: asyncpg.Connection,
        *,
        actor: CurrentUser,
        status: str | None,
        triage_tier: int | None,
        assigned_to: UUID | None,
        q: str | None,
        page_size: int,
        offset: int,
        order_by: str,
    ):
        if not is_staff(actor):
            raise Forbidden("Staff access required")
        return await self.repo.list_complaints(
            conn,
            user_id=None,
            status=status,
            triage_tier=triage_tier,
            assigned_to=assigned_to,
            q=q,
            page_size=page_size,
            offset=offset,
            order_by=order_by,
        )

    async def update_case(
        self,
        conn: asyncpg.Connection,
        *,
        actor: CurrentUser,
        complaint_id: UUID,
        payload: CaseUpdate,
        request: RequestInfo,
    ) -> asyncpg.Record:
        if not is_staff(actor):
            raise Forbidden("Staff access required")
        complaint = await self.repo.get(conn, complaint_id)
        if complaint is None:
            raise NotFound("Complaint not found")
        if payload.status and not can_transition(
            COMPLAINT_TRANSITIONS, str(complaint["status"]), payload.status.value
        ):
            raise Conflict(
                f"Cannot move case from {complaint['status']} to {payload.status.value}",
                code="invalid_transition",
            )
        if payload.assigned_to:
            assignee = await self.users.get_by_id(conn, payload.assigned_to)
            if assignee is None or not is_staff(CurrentUser.from_record(assignee)):
                raise BadRequest("Cases can only be assigned to staff", code="invalid_assignee")
        fields = payload.model_dump(exclude_unset=True)
        fields = {
            key: value for key, value in fields.items() if value is not None or key == "assigned_to"
        }
        fields.pop("note", None)
        async with conn.transaction():
            row = await self.repo.update_case(conn, complaint_id, fields)
            if row is None:
                raise NotFound("Complaint not found")
            if payload.note:
                await self.repo.add_note(
                    conn,
                    complaint_id=complaint_id,
                    author_id=actor.id,
                    body=payload.note,
                )
            if payload.status or payload.assigned_to or payload.triage_tier:
                await self.notifications.request_delivery(
                    conn,
                    user_id=complaint["user_id"],
                    notification_type=NotificationType.COMPLAINT_UPDATE,
                    title="Case updated",
                    body=f"Your case is now {row['status']}.",
                    data={"complaint_id": str(complaint_id)},
                    deep_link=f"videshamitra://complaints/{complaint_id}",
                    channels=["push", "in_app"],
                )
            await self.audit.record(
                conn,
                actor=actor,
                action="case.updated",
                entity_type="complaint",
                entity_id=complaint_id,
                request=request,
                metadata={
                    "fields": sorted(fields),
                    "has_note": bool(payload.note),
                },
            )
        return row

    async def add_note(
        self,
        conn: asyncpg.Connection,
        *,
        actor: CurrentUser,
        complaint_id: UUID,
        payload: CaseNoteCreate,
        request: RequestInfo,
    ) -> asyncpg.Record:
        if not is_staff(actor):
            raise Forbidden("Staff access required")
        complaint = await self.repo.get(conn, complaint_id)
        if complaint is None:
            raise NotFound("Complaint not found")
        note = await self.repo.add_note(
            conn,
            complaint_id=complaint_id,
            author_id=actor.id,
            body=payload.body,
            is_internal=payload.is_internal,
        )
        await self.audit.record(
            conn,
            actor=actor,
            action="case.note_added",
            entity_type="complaint",
            entity_id=complaint_id,
            request=request,
            metadata={"note_id": str(note["id"])},
        )
        return note

    async def escalate_case(
        self,
        conn: asyncpg.Connection,
        *,
        actor: CurrentUser,
        complaint_id: UUID,
        payload: CaseEscalate,
        request: RequestInfo,
    ) -> asyncpg.Record:
        if not is_staff(actor):
            raise Forbidden("Staff access required")
        complaint = await self.repo.get(conn, complaint_id)
        if complaint is None:
            raise NotFound("Complaint not found")
        if complaint["status"] in (ComplaintStatus.RESOLVED, ComplaintStatus.CLOSED):
            raise Conflict("This case is already closed", code="invalid_transition")
        async with conn.transaction():
            row = await self.repo.update_case(
                conn,
                complaint_id,
                {"status": ComplaintStatus.ESCALATED.value, "triage_tier": payload.triage_tier},
            )
            if payload.reason:
                await self.repo.add_note(
                    conn,
                    complaint_id=complaint_id,
                    author_id=actor.id,
                    body=payload.reason,
                )
            await self.notifications.request_delivery(
                conn,
                user_id=complaint["user_id"],
                notification_type=NotificationType.COMPLAINT_UPDATE,
                title="Case escalated",
                body="Your case has been escalated to a senior caseworker.",
                data={"complaint_id": str(complaint_id)},
                deep_link=f"videshamitra://complaints/{complaint_id}",
                channels=["push", "in_app"],
            )
            await self.audit.record(
                conn,
                actor=actor,
                action="case.escalated",
                entity_type="complaint",
                entity_id=complaint_id,
                request=request,
                metadata={"tier": payload.triage_tier, "has_reason": bool(payload.reason)},
            )
        return row

    async def create_or_escalate_from_checkin(
        self,
        conn: asyncpg.Connection,
        *,
        checkin: Any,
        reason: str,
        triage_tier: int = 2,
        risk_level: RiskLevel | None = None,
    ) -> UUID:
        """System path: high-risk or missed check-in creates/escalates a case."""
        existing = await self.repo.open_complaint_for_user(conn, checkin["user_id"])
        title = "Check-in follow-up required"
        if existing is None:
            created = await self.repo.create(
                conn,
                user_id=checkin["user_id"],
                title=title,
                description=reason,
                journey_id=checkin["journey_id"],
                verification_id=None,
                agency_id=checkin["agency_id"],
                checkin_id=checkin["id"],
                triage_tier=triage_tier,
                evidence=[{"checkin_id": str(checkin["id"]), "risk_level": risk_level}]
                if risk_level
                else [],
            )
            await self.repo.update_case(
                conn,
                created["id"],
                {
                    "status": ComplaintStatus.SUBMITTED.value,
                    "triage_tier": triage_tier,
                },
            )
            await conn.execute(
                "update core.complaints set submitted_at = now() where id = $1",
                created["id"],
            )
            complaint_id = created["id"]
        else:
            complaint_id = existing["id"]
            await self.repo.update_case(
                conn,
                complaint_id,
                {
                    "status": ComplaintStatus.ESCALATED.value,
                    "triage_tier": max(int(existing["triage_tier"]), triage_tier),
                },
            )
            await self.repo.add_note(
                conn,
                complaint_id=complaint_id,
                author_id=None,
                body=reason,
            )
        await self.notifications.notify_staff(
            conn,
            title="Check-in escalation",
            body=reason,
            data={"complaint_id": str(complaint_id)},
            deep_link=f"videshamitra://admin/cases/{complaint_id}",
        )
        await self.audit.record(
            conn,
            actor=None,
            action="case.created_from_checkin",
            entity_type="complaint",
            entity_id=complaint_id,
            metadata={"tier": triage_tier, "checkin_id": str(checkin["id"])},
            actor_service="core-api-worker",
        )
        return complaint_id
