"""Agency search, admin maintenance, SLBFE import and license watchdog."""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime, timedelta
from uuid import UUID

import asyncpg

from app.core.exceptions import Conflict, NotFound, UpstreamError
from app.integrations.slbfe.import_service import ImportSummary, SLBFEImporter
from app.models.entities import CurrentUser, RequestInfo
from app.models.enums import NotificationType
from app.repositories.agency_repository import AgencyRepository
from app.schemas.agency import AgencyCreate, AgencyUpdate
from app.services.audit_service import AuditService
from app.services.notification_service import NotificationService
from app.utils.text import normalize_name

logger = logging.getLogger(__name__)


class AgencyService:
    def __init__(
        self,
        repo: AgencyRepository | None = None,
        audit: AuditService | None = None,
        notifications: NotificationService | None = None,
        importer: SLBFEImporter | None = None,
    ) -> None:
        self.repo = repo or AgencyRepository()
        self.audit = audit or AuditService()
        self.notifications = notifications or NotificationService()
        self.importer = importer or SLBFEImporter(self.repo)

    async def search(
        self,
        conn: asyncpg.Connection,
        *,
        q: str | None,
        status: str | None,
        district: str | None,
        page_size: int,
        offset: int,
        order_by: str | None = None,
    ):
        from app.utils.text import normalize_name as _normalize

        return await self.repo.search(
            conn,
            q=_normalize(q),
            status=status,
            district=district,
            page_size=page_size,
            offset=offset,
            order_by=order_by,
        )

    async def get(self, conn: asyncpg.Connection, agency_id: UUID) -> asyncpg.Record:
        row = await self.repo.get(conn, agency_id)
        if row is None:
            raise NotFound("Agency not found")
        return row

    async def license_history(
        self, conn: asyncpg.Connection, agency_id: UUID
    ) -> list[asyncpg.Record]:
        await self.get(conn, agency_id)
        return await self.repo.list_licenses(conn, agency_id)

    async def create(
        self,
        conn: asyncpg.Connection,
        *,
        actor: CurrentUser,
        payload: AgencyCreate,
        request: RequestInfo,
    ) -> asyncpg.Record:
        existing = await self.repo.get_by_registration(conn, payload.registration_no)
        if existing is not None:
            raise Conflict("An agency with this registration number already exists")
        data = payload.model_dump()
        data["normalized_name"] = normalize_name(payload.name)
        try:
            row = await self.repo.create(conn, data)
        except asyncpg.UniqueViolationError as exc:
            raise Conflict("An agency with this registration number already exists") from exc
        await self.audit.record(
            conn,
            actor=actor,
            action="agency.created",
            entity_type="agency",
            entity_id=row["id"],
            request=request,
            metadata={"registration_no": payload.registration_no},
        )
        return row

    async def update(
        self,
        conn: asyncpg.Connection,
        *,
        actor: CurrentUser,
        agency_id: UUID,
        payload: AgencyUpdate,
        request: RequestInfo,
    ) -> asyncpg.Record:
        await self.get(conn, agency_id)
        data = payload.model_dump(exclude_unset=True)
        if "name" in data and data["name"]:
            data["normalized_name"] = normalize_name(data["name"])
        row = await self.repo.update(conn, agency_id, data)
        if row is None:
            raise NotFound("Agency not found")
        await self.audit.record(
            conn,
            actor=actor,
            action="agency.updated",
            entity_type="agency",
            entity_id=agency_id,
            request=request,
            metadata={"fields": sorted(data)},
        )
        return row

    async def import_agencies(
        self,
        conn: asyncpg.Connection,
        *,
        actor: CurrentUser,
        snapshot_date: date | None,
        dry_run: bool,
        request: RequestInfo,
    ) -> ImportSummary:
        try:
            async with conn.transaction():
                summary = await self.importer.import_from_source(
                    conn,
                    snapshot_date=snapshot_date,
                    imported_by=actor.id,
                    dry_run=dry_run,
                )
                if not dry_run:
                    await self.audit.record(
                        conn,
                        actor=actor,
                        action="agency.imported",
                        entity_type="agency_snapshot",
                        entity_id=summary.snapshot_id,
                        request=request,
                        metadata={
                            "parsed": summary.parsed,
                            "imported": summary.inserted_or_updated,
                            "duplicate": summary.duplicate_snapshot,
                        },
                    )
            return summary
        except UpstreamError:
            raise
        except Exception as exc:
            logger.exception("agency_import_failed")
            raise UpstreamError("Agency import failed", service="slbfe", details=str(exc)) from exc

    async def list_snapshots(self, conn: asyncpg.Connection, *, page_size: int, offset: int):
        return await self.repo.list_snapshots(conn, limit=page_size, offset=offset)

    async def process_license_changes(
        self, conn: asyncpg.Connection, *, since: datetime | None = None
    ) -> int:
        """Notify affected workers about suspended/expired/cancelled licenses."""
        since = since or (datetime.now(UTC) - timedelta(hours=2))
        changes = await self.repo.license_changes_since(conn, since)
        sent = 0
        for change in changes:
            already = await self.repo.alert_already_sent(
                conn,
                agency_id=change["id"],
                license_no=change["license_no"],
                status=change["license_status"],
            )
            if already:
                continue
            workers = await self.repo.workers_for_agency(conn, change["id"])
            for user_id in workers:
                await self.notifications.request_delivery(
                    conn,
                    user_id=user_id,
                    notification_type=NotificationType.AGENCY_LICENSE_CHANGED,
                    title="Agency license alert",
                    body=(
                        f"The license for {change['name']} is now "
                        f"{change['license_status']}. Review your job offer."
                    ),
                    data={
                        "agency_id": str(change["id"]),
                        "license_no": change["license_no"],
                        "license_status": str(change["license_status"]),
                    },
                    deep_link=f"videshamitra://agencies/{change['id']}",
                    channels=["push", "whatsapp"],
                )
                sent += 1
        if sent:
            logger.info("agency_license_alerts_sent", extra={"count": sent})
        return sent
