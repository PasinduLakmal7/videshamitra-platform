"""Verification orchestration and the pending -> processing -> result machine."""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

import asyncpg

from app.core.config import settings
from app.core.exceptions import BadRequest, Conflict, Forbidden, NotFound
from app.core.permissions import is_admin, is_staff
from app.events.envelope import enqueue_event
from app.events.schemas import (
    AgencyRef,
    DocumentRef,
    JobDetails,
    VerificationCompletedEvent,
    VerificationFailedEvent,
    VerificationRequestedData,
)
from app.models.entities import CurrentUser, RequestInfo
from app.models.enums import (
    VERIFICATION_TRANSITIONS,
    DocumentStatus,
    NotificationType,
    VerificationStatus,
    can_transition,
)
from app.repositories.agency_repository import AgencyRepository
from app.repositories.document_repository import DocumentRepository
from app.repositories.verification_repository import VerificationRepository
from app.schemas.verification import VerificationCreate, VerificationReview
from app.services.audit_service import AuditService
from app.services.notification_service import NotificationService
from app.utils.text import normalize_name

logger = logging.getLogger(__name__)


class VerificationService:
    def __init__(
        self,
        repo: VerificationRepository | None = None,
        documents: DocumentRepository | None = None,
        agencies: AgencyRepository | None = None,
        notifications: NotificationService | None = None,
        audit: AuditService | None = None,
    ) -> None:
        self.repo = repo or VerificationRepository()
        self.documents = documents or DocumentRepository()
        self.agencies = agencies or AgencyRepository()
        self.notifications = notifications or NotificationService()
        self.audit = audit or AuditService()

    async def _build_event_data(
        self,
        conn: asyncpg.Connection,
        *,
        verification: asyncpg.Record,
        user: CurrentUser,
        document_ids: list[UUID],
    ) -> dict[str, Any]:
        agency = None
        if verification["agency_id"]:
            row = await self.agencies.get(conn, verification["agency_id"])
            if row is not None:
                agency = AgencyRef(
                    id=row["id"],
                    registration_no=row["registration_no"],
                    name=row["name"],
                    license_no=row["license_no"],
                    license_status=str(row["license_status"]),
                    license_expires_on=(
                        row["license_expires_on"].isoformat() if row["license_expires_on"] else None
                    ),
                )
        if agency is None and verification["agency_name_input"]:
            agency = AgencyRef(
                name=verification["agency_name_input"],
                license_status="unknown",
            )

        docs: list[DocumentRef] = []
        for document_id in document_ids:
            row = await self.documents.get(conn, document_id)
            if row is None:
                continue
            docs.append(
                DocumentRef(
                    document_id=row["id"],
                    type=str(row["type"]),
                    mime_type=row["mime_type"],
                    page_count=row["page_count"],
                )
            )

        payload = VerificationRequestedData(
            verification_id=verification["id"],
            user_id=verification["user_id"],
            locale=user.preferred_language.value,
            agency=agency,
            job=JobDetails(
                title=verification["job_title"],
                employer_name=verification["employer_name"],
                destination_country=verification["destination_country"],
                offered_salary=(
                    float(verification["offered_salary"])
                    if verification["offered_salary"] is not None
                    else None
                ),
                currency=verification["currency"],
            ),
            documents=docs,
        )
        return payload.model_dump(mode="json")

    async def create(
        self,
        conn: asyncpg.Connection,
        *,
        actor: CurrentUser,
        payload: VerificationCreate,
        request: RequestInfo,
    ) -> asyncpg.Record:
        async with conn.transaction():
            documents = []
            for document_id in payload.document_ids:
                row = await self.documents.get(conn, document_id)
                if row is None:
                    raise BadRequest(
                        "One or more documents were not found",
                        code="document_not_found",
                        details={"document_id": str(document_id)},
                    )
                if row["user_id"] != actor.id:
                    raise Forbidden("You can only attach your own documents")
                documents.append(row)

            agency_id = payload.agency_id
            if agency_id is not None:
                agency = await self.agencies.get(conn, agency_id)
                if agency is None:
                    raise BadRequest("Agency not found", code="agency_not_found")
            elif payload.agency_name_input:
                match = await self.agencies.find_best_match(
                    conn, normalize_name(payload.agency_name_input)
                )
                agency_id = match["id"] if match else None

            verification = await self.repo.create(
                conn,
                user_id=actor.id,
                agency_id=agency_id,
                agency_name_input=payload.agency_name_input,
                job_title=payload.job_title,
                employer_name=payload.employer_name,
                destination_country=payload.destination_country,
                offered_salary=payload.offered_salary,
                currency=payload.currency,
            )
            if payload.document_ids:
                await self.documents.link_to_verification(
                    conn,
                    verification_id=verification["id"],
                    user_id=actor.id,
                    document_ids=payload.document_ids,
                )
            event_data = await self._build_event_data(
                conn,
                verification=verification,
                user=actor,
                document_ids=payload.document_ids,
            )
            await enqueue_event(
                conn,
                event_type="verification.requested",
                data=event_data,
                stream=settings.AI_REQUESTS_STREAM,
            )
            await self.audit.record(
                conn,
                actor=actor,
                action="verification.created",
                entity_type="verification",
                entity_id=verification["id"],
                request=request,
                metadata={
                    "agency_id": str(agency_id) if agency_id else None,
                    "documents": len(payload.document_ids),
                },
            )
        created = await self.repo.get(conn, verification["id"])
        assert created is not None
        return created

    async def get(
        self,
        conn: asyncpg.Connection,
        *,
        actor: CurrentUser,
        verification_id: UUID,
    ) -> asyncpg.Record:
        row = await self.repo.get(conn, verification_id)
        if row is None:
            raise NotFound("Verification not found")
        if row["user_id"] != actor.id and not is_staff(actor):
            raise Forbidden("You do not have access to this verification")
        return row

    async def list_verifications(
        self,
        conn: asyncpg.Connection,
        *,
        actor: CurrentUser,
        user_id: UUID | None,
        status: str | None,
        risk_level: str | None,
        agency_id: UUID | None,
        q: str | None,
        page_size: int,
        offset: int,
        order_by: str,
    ):
        effective_user = user_id if is_staff(actor) else actor.id
        return await self.repo.list_verifications(
            conn,
            user_id=effective_user,
            status=status,
            risk_level=risk_level,
            agency_id=agency_id,
            q=q,
            page_size=page_size,
            offset=offset,
            order_by=order_by,
        )

    async def retry(
        self,
        conn: asyncpg.Connection,
        *,
        actor: CurrentUser,
        verification_id: UUID,
        request: RequestInfo,
        force: bool = False,
    ) -> asyncpg.Record:
        row = await self.repo.get(conn, verification_id)
        if row is None:
            raise NotFound("Verification not found")
        if row["user_id"] != actor.id and not is_admin(actor) and not (force and is_staff(actor)):
            raise Forbidden("You cannot retry this verification")
        if row["status"] in (VerificationStatus.PENDING, VerificationStatus.PROCESSING):
            # Retrying an already-queued job is a no-op, not a conflict.
            return row
        if row["status"] != VerificationStatus.FAILED and not force:
            raise Conflict(
                "Only failed verifications can be retried",
                code="retry_not_allowed",
            )

        async with conn.transaction():
            updated = await self.repo.mark_retry(conn, verification_id)
            if updated is None:  # pragma: no cover
                raise NotFound("Verification not found")
            document_rows, _ = await self.documents.list_documents(
                conn,
                user_id=None,
                verification_id=verification_id,
                document_type=None,
                page_size=100,
                offset=0,
                order_by="created_at ASC",
            )
            document_ids = [doc["id"] for doc in document_rows]
            for document_id in document_ids:
                await self.documents.update_status(
                    conn, document_id, DocumentStatus.PROCESSING.value
                )
            owner = await conn.fetchrow("select * from core.users where id = $1", row["user_id"])
            event_actor = CurrentUser.from_record(owner) if owner else actor
            event_data = await self._build_event_data(
                conn,
                verification=updated,
                user=event_actor,
                document_ids=document_ids,
            )
            await enqueue_event(
                conn,
                event_type="verification.requested",
                data=event_data,
                stream=settings.AI_REQUESTS_STREAM,
            )
            await self.audit.record(
                conn,
                actor=actor,
                action="verification.retried",
                entity_type="verification",
                entity_id=verification_id,
                request=request,
                metadata={"retry_count": updated["retry_count"]},
            )
        refreshed = await self.repo.get(conn, verification_id)
        assert refreshed is not None
        return refreshed

    async def review(
        self,
        conn: asyncpg.Connection,
        *,
        actor: CurrentUser,
        verification_id: UUID,
        payload: VerificationReview,
        request: RequestInfo,
    ) -> asyncpg.Record:
        if not is_staff(actor):
            raise Forbidden("Staff access required")
        row = await self.repo.get(conn, verification_id)
        if row is None:
            raise NotFound("Verification not found")
        if not can_transition(VERIFICATION_TRANSITIONS, str(row["status"]), payload.status.value):
            raise Conflict(
                f"Cannot move verification from {row['status']} to {payload.status.value}",
                code="invalid_transition",
            )
        if (
            payload.risk_level is None
            and row["risk_level"] is None
            and payload.status
            in (
                VerificationStatus.VERIFIED,
                VerificationStatus.SUSPICIOUS,
                VerificationStatus.FRAUDULENT,
            )
        ):
            # A manual verdict must state its risk.
            raise BadRequest("risk_level is required for a manual verdict")

        updated = await self.repo.review(
            conn,
            verification_id=verification_id,
            status=payload.status.value,
            risk_level=payload.risk_level.value if payload.risk_level else None,
            risk_score=payload.risk_score,
            findings=payload.findings,
            reviewed_by=actor.id,
        )
        if updated is None:  # pragma: no cover
            raise NotFound("Verification not found")
        await self.notifications.request_delivery(
            conn,
            user_id=row["user_id"],
            notification_type=NotificationType.VERIFICATION_COMPLETE,
            title="Verification updated",
            body=f"A caseworker reviewed your verification: {payload.status.value}.",
            data={"verification_id": str(verification_id)},
            deep_link=f"videshamitra://verifications/{verification_id}",
            channels=["push"],
        )
        await self.audit.record(
            conn,
            actor=actor,
            action="verification.reviewed",
            entity_type="verification",
            entity_id=verification_id,
            request=request,
            metadata={
                "status": payload.status.value,
                "risk_level": payload.risk_level.value if payload.risk_level else None,
                "has_note": bool(payload.note),
            },
        )
        refreshed = await self.repo.get(conn, verification_id)
        assert refreshed is not None
        return refreshed

    async def handle_result(self, conn: asyncpg.Connection, event: dict[str, Any]) -> bool:
        """Apply a completed/failed event. Caller owns the dedupe transaction."""
        event_type = event.get("event_type")
        if event_type == "verification.completed":
            completed = VerificationCompletedEvent.model_validate(event)
            data = completed.data
            updated = await self.repo.apply_result(
                conn,
                verification_id=data.verification_id,
                status=data.status,
                risk_level=data.risk_level,
                risk_score=data.risk_score,
                findings=[item.model_dump(mode="json") for item in data.findings],
                evidence=[item.model_dump(mode="json") for item in data.evidence],
                engine_version=data.engine_version,
                analysis_run_id=data.analysis_run_id,
            )
            if updated is None:
                logger.info(
                    "verification_result_ignored",
                    extra={"verification_id": str(data.verification_id)},
                )
                return False
            await self._mark_documents(conn, data.verification_id, DocumentStatus.PROCESSED)
            await self._notify_result(
                conn,
                verification=updated,
                status=data.status,
                risk_level=data.risk_level,
            )
            await self.audit.record(
                conn,
                actor=None,
                action="verification.result_applied",
                entity_type="verification",
                entity_id=data.verification_id,
                metadata={
                    "status": data.status,
                    "risk_level": data.risk_level,
                    "analysis_run_id": data.analysis_run_id,
                },
                actor_service="ai-service",
            )
            return True

        if event_type == "verification.failed":
            failed = VerificationFailedEvent.model_validate(event)
            data = failed.data
            updated = await self.repo.apply_failure(
                conn,
                verification_id=data.verification_id,
                error_code=data.error_code,
                message=data.message,
            )
            if updated is None:
                return False
            await self._mark_documents(conn, data.verification_id, DocumentStatus.FAILED)
            await self.notifications.request_delivery(
                conn,
                user_id=updated["user_id"],
                notification_type=NotificationType.VERIFICATION_COMPLETE,
                title="Verification could not be completed",
                body="We could not analyse your documents. Please retry or upload clearer copies.",
                data={
                    "verification_id": str(data.verification_id),
                    "error_code": data.error_code,
                },
                deep_link=f"videshamitra://verifications/{data.verification_id}",
                channels=["push"],
            )
            await self.audit.record(
                conn,
                actor=None,
                action="verification.failed",
                entity_type="verification",
                entity_id=data.verification_id,
                metadata={"error_code": data.error_code, "retryable": data.retryable},
                actor_service="ai-service",
            )
            return True

        logger.warning("unknown_verification_event", extra={"event_type": event_type})
        return False

    async def _mark_documents(
        self, conn: asyncpg.Connection, verification_id: UUID, status: DocumentStatus
    ) -> None:
        await conn.execute(
            """
            update core.documents
            set status = $2::core.document_status
            where verification_id = $1 and deleted_at is null
            """,
            verification_id,
            status.value,
        )

    async def _notify_result(
        self,
        conn: asyncpg.Connection,
        *,
        verification: asyncpg.Record,
        status: str,
        risk_level: str | None,
    ) -> None:
        if status == "verified" and risk_level in ("low", "medium"):
            title = "Verification complete"
            body = "Your job offer passed verification. Tap to see the details."
        else:
            title = "Verification complete"
            body = "Your job offer has a high-risk finding. Tap to review."
        await self.notifications.request_delivery(
            conn,
            user_id=verification["user_id"],
            notification_type=NotificationType.VERIFICATION_COMPLETE,
            title=title,
            body=body,
            data={
                "verification_id": str(verification["id"]),
                "status": status,
                "risk_level": risk_level,
            },
            deep_link=f"videshamitra://verifications/{verification['id']}",
            channels=["push", "whatsapp"],
        )

    async def recover_stale(self, conn: asyncpg.Connection) -> int:
        stale = await self.repo.stale_processing(conn, minutes=settings.STALE_PROCESSING_MINUTES)
        recovered = 0
        for row in stale:
            async with conn.transaction():
                updated = await self.repo.mark_retry(conn, row["id"])
                if updated is None:
                    continue
                document_rows, _ = await self.documents.list_documents(
                    conn,
                    user_id=None,
                    verification_id=row["id"],
                    document_type=None,
                    page_size=100,
                    offset=0,
                    order_by="created_at ASC",
                )
                document_ids = [doc["id"] for doc in document_rows]
                user = await conn.fetchrow("select * from core.users where id = $1", row["user_id"])
                if user is None:
                    continue
                actor = CurrentUser.from_record(user)
                event_data = await self._build_event_data(
                    conn,
                    verification=updated,
                    user=actor,
                    document_ids=document_ids,
                )
                await enqueue_event(
                    conn,
                    event_type="verification.requested",
                    data=event_data,
                    stream=settings.AI_REQUESTS_STREAM,
                )
                await self.audit.record(
                    conn,
                    actor=None,
                    action="verification.stale_recovered",
                    entity_type="verification",
                    entity_id=row["id"],
                    metadata={"retry_count": updated["retry_count"]},
                    actor_service="core-api-worker",
                )
                recovered += 1
        return recovered
