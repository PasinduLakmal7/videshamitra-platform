"""SLBFE import: snapshot, upsert agencies, append license history."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID

import asyncpg

from app.integrations.slbfe.client import fetch_and_parse
from app.integrations.slbfe.parser import ParseResult
from app.repositories.agency_repository import AgencyRepository

logger = logging.getLogger(__name__)


@dataclass
class ImportSummary:
    snapshot_id: UUID | None
    snapshot_date: date
    checksum: str
    parsed: int
    inserted_or_updated: int
    errors: list[str]
    duplicate_snapshot: bool = False
    dry_run: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "snapshot_id": str(self.snapshot_id) if self.snapshot_id else None,
            "snapshot_date": self.snapshot_date.isoformat(),
            "checksum": self.checksum,
            "parsed": self.parsed,
            "imported": self.inserted_or_updated,
            "errors": self.errors,
            "duplicate_snapshot": self.duplicate_snapshot,
            "dry_run": self.dry_run,
        }


class SLBFEImporter:
    def __init__(self, repo: AgencyRepository | None = None) -> None:
        self.repo = repo or AgencyRepository()

    async def import_payload(
        self,
        conn: asyncpg.Connection,
        *,
        parsed: ParseResult,
        checksum: str,
        source_url: str | None,
        snapshot_date: date | None = None,
        imported_by: UUID | None = None,
        dry_run: bool = False,
    ) -> ImportSummary:
        snapshot_date = snapshot_date or datetime.now(UTC).date()
        if dry_run:
            return ImportSummary(
                snapshot_id=None,
                snapshot_date=snapshot_date,
                checksum=checksum,
                parsed=parsed.record_count,
                inserted_or_updated=0,
                errors=parsed.errors,
                dry_run=True,
            )

        snapshot, created = await self.repo.create_snapshot(
            conn,
            snapshot_date=snapshot_date,
            source_url=source_url,
            checksum=checksum,
            record_count=parsed.record_count,
            imported_by=imported_by,
        )
        if not created:
            logger.info("slbfe_duplicate_snapshot", extra={"checksum": checksum})
            return ImportSummary(
                snapshot_id=snapshot["id"],
                snapshot_date=snapshot_date,
                checksum=checksum,
                parsed=parsed.record_count,
                inserted_or_updated=0,
                errors=parsed.errors,
                duplicate_snapshot=True,
            )

        imported = 0
        seen: set[str] = set()
        for record in parsed.records:
            if record.registration_no in seen:
                # Later rows win, but only insert history once per snapshot.
                logger.warning(
                    "slbfe_duplicate_registration",
                    extra={"registration_no": record.registration_no},
                )
            seen.add(record.registration_no)
            agency = await self.repo.upsert_imported_agency(
                conn,
                registration_no=record.registration_no,
                name=record.name,
                normalized_name=record.normalized_name,
                license_no=record.license_no,
                license_status=record.license_status.value,
                license_expires_on=record.license_expires_on,
                address=record.address,
                district=record.district,
                phone=record.phone,
                email=record.email,
                snapshot_id=snapshot["id"],
            )
            await self.repo.add_license_history(
                conn,
                agency_id=agency["id"],
                snapshot_id=snapshot["id"],
                license_no=record.license_no,
                status=record.license_status.value,
                issued_on=record.issued_on,
                expires_on=record.license_expires_on,
                job_categories=record.job_categories or None,
                raw_data=record.raw_data,
            )
            imported += 1

        return ImportSummary(
            snapshot_id=snapshot["id"],
            snapshot_date=snapshot_date,
            checksum=checksum,
            parsed=parsed.record_count,
            inserted_or_updated=imported,
            errors=parsed.errors,
        )

    async def import_from_source(
        self,
        conn: asyncpg.Connection,
        *,
        source: str | None = None,
        snapshot_date: date | None = None,
        imported_by: UUID | None = None,
        dry_run: bool = False,
    ) -> ImportSummary:
        fetched, parsed = await fetch_and_parse(source)
        return await self.import_payload(
            conn,
            parsed=parsed,
            checksum=fetched.checksum,
            source_url=fetched.source_url,
            snapshot_date=snapshot_date,
            imported_by=imported_by,
            dry_run=dry_run,
        )
