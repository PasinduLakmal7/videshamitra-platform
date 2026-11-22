"""SQL for agencies, snapshots, license history and affected workers."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID

import asyncpg

SORT_COLUMNS = {
    "name": "name",
    "created_at": "created_at",
    "updated_at": "updated_at",
    "license_expires_on": "license_expires_on",
    "district": "district",
}


class AgencyRepository:
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
    ) -> tuple[list[asyncpg.Record], int]:
        raw_q = (q or "").strip()
        normalized = raw_q.lower()
        status_value = status or ""
        district_value = (district or "").strip()

        where = """
            where (
                $1::text = ''
                or normalized_name like '%' || $1 || '%'
                or similarity(normalized_name, $1) > 0.18
                or name ilike '%' || $2 || '%'
                or registration_no ilike '%' || $2 || '%'
            )
            and ($3::text = '' or license_status::text = $3)
            and ($4::text = '' or district ilike '%' || $4 || '%')
        """
        params = [normalized, raw_q, status_value, district_value]
        total = await conn.fetchval(f"select count(*) from core.agencies {where}", *params)
        if order_by is None:
            order_by = (
                "similarity(normalized_name, $1) desc, name asc" if normalized else "name asc"
            )
        rows = await conn.fetch(
            f"""
            select id, registration_no, name, normalized_name, license_no,
                   license_status, license_expires_on, address, district, phone,
                   email, latest_snapshot_id, created_at, updated_at
            from core.agencies
            {where}
            order by {order_by}
            limit $5 offset $6
            """,
            *params,
            page_size,
            offset,
        )
        return list(rows), int(total or 0)

    async def get(self, conn: asyncpg.Connection, agency_id: UUID) -> asyncpg.Record | None:
        return await conn.fetchrow(
            """
            select id, registration_no, name, normalized_name, license_no,
                   license_status, license_expires_on, address, district, phone,
                   email, latest_snapshot_id, created_at, updated_at
            from core.agencies where id = $1
            """,
            agency_id,
        )

    async def get_by_registration(
        self, conn: asyncpg.Connection, registration_no: str
    ) -> asyncpg.Record | None:
        return await conn.fetchrow(
            """
            select id, registration_no, name, normalized_name, license_no,
                   license_status, license_expires_on, address, district, phone,
                   email, latest_snapshot_id, created_at, updated_at
            from core.agencies where registration_no = $1
            """,
            registration_no,
        )

    async def find_best_match(self, conn: asyncpg.Connection, name: str) -> asyncpg.Record | None:
        normalized = name.lower().strip()
        if not normalized:
            return None
        return await conn.fetchrow(
            """
            select id, registration_no, name, license_no, license_status,
                   license_expires_on, similarity(normalized_name, $1) as score
            from core.agencies
            where similarity(normalized_name, $1) > 0.25
               or normalized_name like '%' || $1 || '%'
            order by similarity(normalized_name, $1) desc
            limit 1
            """,
            normalized,
        )

    async def create(self, conn: asyncpg.Connection, data: dict[str, Any]) -> asyncpg.Record:
        return await conn.fetchrow(
            """
            insert into core.agencies
                (registration_no, name, normalized_name, license_no, license_status,
                 license_expires_on, address, district, phone, email, latest_snapshot_id)
            values ($1, $2, $3, $4, $5::core.agency_license_status, $6, $7, $8, $9, $10, $11)
            returning *
            """,
            data["registration_no"],
            data["name"],
            data["normalized_name"],
            data.get("license_no"),
            data.get("license_status", "unknown"),
            data.get("license_expires_on"),
            data.get("address"),
            data.get("district"),
            data.get("phone"),
            data.get("email"),
            data.get("latest_snapshot_id"),
        )

    async def update(
        self, conn: asyncpg.Connection, agency_id: UUID, data: dict[str, Any]
    ) -> asyncpg.Record | None:
        allowed = [
            "name",
            "normalized_name",
            "license_no",
            "license_status",
            "license_expires_on",
            "address",
            "district",
            "phone",
            "email",
        ]
        updates = {key: value for key, value in data.items() if key in allowed}
        if not updates:
            return await self.get(conn, agency_id)
        set_parts = []
        values: list[Any] = []
        for index, (column, value) in enumerate(updates.items(), start=1):
            cast = "::core.agency_license_status" if column == "license_status" else ""
            set_parts.append(f"{column} = ${index}{cast}")
            values.append(value)
        values.append(agency_id)
        return await conn.fetchrow(
            f"""
            update core.agencies
            set {", ".join(set_parts)}
            where id = ${len(values)}
            returning *
            """,
            *values,
        )

    async def list_licenses(
        self, conn: asyncpg.Connection, agency_id: UUID
    ) -> list[asyncpg.Record]:
        return list(
            await conn.fetch(
                """
                select id, agency_id, snapshot_id, license_no, status,
                       issued_on, expires_on, job_categories, raw_data, created_at
                from core.agency_license_history
                where agency_id = $1
                order by created_at desc
                """,
                agency_id,
            )
        )

    async def create_snapshot(
        self,
        conn: asyncpg.Connection,
        *,
        snapshot_date: date,
        source_url: str | None,
        checksum: str,
        record_count: int,
        imported_by: UUID | None,
    ) -> tuple[asyncpg.Record, bool]:
        row = await conn.fetchrow(
            """
            insert into core.agency_snapshots
                (snapshot_date, source_url, checksum, record_count, imported_by)
            values ($1, $2, $3, $4, $5)
            on conflict (snapshot_date, checksum) do nothing
            returning *
            """,
            snapshot_date,
            source_url,
            checksum,
            record_count,
            imported_by,
        )
        if row is not None:
            return row, True
        existing = await conn.fetchrow(
            """
            select * from core.agency_snapshots
            where snapshot_date = $1 and checksum = $2
            """,
            snapshot_date,
            checksum,
        )
        if existing is None:  # pragma: no cover - unique constraint guarantee
            raise RuntimeError("snapshot upsert failed")
        return existing, False

    async def upsert_imported_agency(
        self,
        conn: asyncpg.Connection,
        *,
        registration_no: str,
        name: str,
        normalized_name: str,
        license_no: str | None,
        license_status: str,
        license_expires_on: date | None,
        address: str | None,
        district: str | None,
        phone: str | None,
        email: str | None,
        snapshot_id: UUID,
    ) -> asyncpg.Record:
        return await conn.fetchrow(
            """
            insert into core.agencies
                (registration_no, name, normalized_name, license_no, license_status,
                 license_expires_on, address, district, phone, email, latest_snapshot_id)
            values ($1, $2, $3, $4, $5::core.agency_license_status, $6, $7, $8, $9, $10, $11)
            on conflict (registration_no) do update
            set name = excluded.name,
                normalized_name = excluded.normalized_name,
                license_no = excluded.license_no,
                license_status = excluded.license_status,
                license_expires_on = excluded.license_expires_on,
                address = excluded.address,
                district = excluded.district,
                phone = excluded.phone,
                email = excluded.email,
                latest_snapshot_id = excluded.latest_snapshot_id
            returning *
            """,
            registration_no,
            name,
            normalized_name,
            license_no,
            license_status,
            license_expires_on,
            address,
            district,
            phone,
            email,
            snapshot_id,
        )

    async def add_license_history(
        self,
        conn: asyncpg.Connection,
        *,
        agency_id: UUID,
        snapshot_id: UUID,
        license_no: str | None,
        status: str,
        issued_on: date | None,
        expires_on: date | None,
        job_categories: list[str] | None,
        raw_data: dict[str, Any],
    ) -> None:
        await conn.execute(
            """
            insert into core.agency_license_history
                (agency_id, snapshot_id, license_no, status, issued_on, expires_on,
                 job_categories, raw_data)
            values ($1, $2, $3, $4::core.agency_license_status, $5, $6, $7, $8)
            on conflict (agency_id, snapshot_id, license_no) do nothing
            """,
            agency_id,
            snapshot_id,
            license_no,
            status,
            issued_on,
            expires_on,
            job_categories,
            raw_data,
        )

    async def list_snapshots(
        self, conn: asyncpg.Connection, *, limit: int = 50, offset: int = 0
    ) -> tuple[list[asyncpg.Record], int]:
        total = await conn.fetchval("select count(*) from core.agency_snapshots")
        rows = await conn.fetch(
            """
            select id, snapshot_date, source_url, checksum, record_count,
                   imported_by, imported_at
            from core.agency_snapshots
            order by snapshot_date desc, imported_at desc
            limit $1 offset $2
            """,
            limit,
            offset,
        )
        return list(rows), int(total or 0)

    async def license_changes_since(
        self, conn: asyncpg.Connection, since: datetime
    ) -> list[asyncpg.Record]:
        return list(
            await conn.fetch(
                """
                select a.id, a.registration_no, a.name, a.license_no,
                       a.license_status, a.license_expires_on, a.updated_at,
                       h.snapshot_id
                from core.agencies a
                left join lateral (
                    select snapshot_id
                    from core.agency_license_history
                    where agency_id = a.id
                    order by created_at desc
                    limit 1
                ) h on true
                where a.license_status in ('suspended', 'expired', 'cancelled')
                  and a.updated_at >= $1
                order by a.updated_at desc
                """,
                since,
            )
        )

    async def alert_already_sent(
        self,
        conn: asyncpg.Connection,
        *,
        agency_id: UUID,
        license_no: str | None,
        status: str,
    ) -> bool:
        exists = await conn.fetchval(
            """
            select 1
            from core.notifications
            where type = 'agency_license_changed'
              and data->>'agency_id' = $1
              and data->>'license_status' = $2
              and coalesce(data->>'license_no', '') = coalesce($3, '')
              and created_at > now() - interval '30 days'
            limit 1
            """,
            str(agency_id),
            status,
            license_no,
        )
        return exists is not None

    async def workers_for_agency(self, conn: asyncpg.Connection, agency_id: UUID) -> list[UUID]:
        rows = await conn.fetch(
            """
            select distinct user_id
            from core.migration_journeys
            where agency_id = $1 and stage <> 'returned'
            union
            select distinct user_id
            from core.verifications
            where agency_id = $1 and created_at > now() - interval '180 days'
            """,
            agency_id,
        )
        return [row["user_id"] for row in rows]
