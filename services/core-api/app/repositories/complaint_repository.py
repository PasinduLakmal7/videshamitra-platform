"""SQL for complaints/cases, evidence links, notes and admin queues."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

import asyncpg

SORT_COLUMNS = {
    "created_at": "created_at",
    "updated_at": "updated_at",
    "submitted_at": "submitted_at",
    "triage_tier": "triage_tier",
    "status": "status",
}


class ComplaintRepository:
    async def create(
        self,
        conn: asyncpg.Connection,
        *,
        user_id: UUID,
        title: str,
        description: str | None,
        journey_id: UUID | None,
        verification_id: UUID | None,
        agency_id: UUID | None,
        checkin_id: UUID | None,
        triage_tier: int = 1,
        evidence: list[dict[str, Any]] | None = None,
        draft_text: str | None = None,
        document_ids: list[UUID] | None = None,
    ) -> asyncpg.Record:
        row = await conn.fetchrow(
            """
            insert into core.complaints
                (user_id, title, description, journey_id, verification_id, agency_id,
                 checkin_id, status, triage_tier, evidence, draft_text)
            values ($1, $2, $3, $4, $5, $6, $7, 'draft', $8, $9, $10)
            returning *
            """,
            user_id,
            title,
            description,
            journey_id,
            verification_id,
            agency_id,
            checkin_id,
            triage_tier,
            evidence or [],
            draft_text,
        )
        if document_ids:
            await self.add_documents(
                conn, complaint_id=row["id"], user_id=user_id, document_ids=document_ids
            )
        return row

    async def get(self, conn: asyncpg.Connection, complaint_id: UUID) -> asyncpg.Record | None:
        return await conn.fetchrow("select * from core.complaints where id = $1", complaint_id)

    async def list_complaints(
        self,
        conn: asyncpg.Connection,
        *,
        user_id: UUID | None,
        status: str | None,
        triage_tier: int | None,
        assigned_to: UUID | None,
        q: str | None,
        page_size: int,
        offset: int,
        order_by: str,
    ) -> tuple[list[asyncpg.Record], int]:
        where = """
            where ($1::uuid is null or c.user_id = $1)
              and ($2::text is null or c.status::text = $2)
              and ($3::integer is null or c.triage_tier = $3)
              and ($4::uuid is null or c.assigned_to = $4)
              and ($5::text is null or c.title ilike '%' || $5 || '%'
                   or c.description ilike '%' || $5 || '%'
                   or u.full_name ilike '%' || $5 || '%')
        """
        params = [user_id, status, triage_tier, assigned_to, q]
        total = await conn.fetchval(
            f"""
            select count(*) from core.complaints c
            join core.users u on u.id = c.user_id
            {where}
            """,
            *params,
        )
        rows = await conn.fetch(
            f"""
            select c.*, u.full_name as worker_name, u.phone as worker_phone,
                   a.name as agency_name
            from core.complaints c
            join core.users u on u.id = c.user_id
            left join core.agencies a on a.id = c.agency_id
            {where}
            order by {order_by}
            limit $6 offset $7
            """,
            *params,
            page_size,
            offset,
        )
        return list(rows), int(total or 0)

    async def update_draft(
        self,
        conn: asyncpg.Connection,
        *,
        complaint_id: UUID,
        user_id: UUID,
        fields: dict[str, Any],
    ) -> asyncpg.Record | None:
        allowed = {"title", "description", "evidence", "draft_text"}
        updates = {key: value for key, value in fields.items() if key in allowed}
        if not updates:
            return await self.get(conn, complaint_id)
        set_parts = []
        values: list[Any] = []
        for index, (column, value) in enumerate(updates.items(), start=1):
            set_parts.append(f"{column} = ${index}")
            values.append(value)
        values.extend([complaint_id, user_id])
        return await conn.fetchrow(
            f"""
            update core.complaints
            set {", ".join(set_parts)}
            where id = ${len(values) - 1} and user_id = ${len(values)} and status = 'draft'
            returning *
            """,
            *values,
        )

    async def update_case(
        self, conn: asyncpg.Connection, complaint_id: UUID, fields: dict[str, Any]
    ) -> asyncpg.Record | None:
        allowed = {
            "status",
            "triage_tier",
            "assigned_to",
            "description",
            "title",
            "evidence",
            "draft_text",
        }
        updates = {key: value for key, value in fields.items() if key in allowed}
        if not updates:
            return await self.get(conn, complaint_id)
        set_parts = []
        values: list[Any] = []
        new_status = updates.pop("status", None)
        if new_status is not None:
            values.append(new_status)
            set_parts.append(f"status = ${len(values)}::core.complaint_status")
        if "assigned_to" in updates:
            values.append(updates.pop("assigned_to"))
            set_parts.append(f"assigned_to = ${len(values)}")
        for column, value in updates.items():
            values.append(value)
            set_parts.append(f"{column} = ${len(values)}")
        if new_status == "resolved":
            set_parts.append("resolved_at = now()")
        values.append(complaint_id)
        return await conn.fetchrow(
            f"""
            update core.complaints
            set {", ".join(set_parts)}
            where id = ${len(values)}
            returning *
            """,
            *values,
        )

    async def submit(
        self, conn: asyncpg.Connection, *, complaint_id: UUID, user_id: UUID
    ) -> asyncpg.Record | None:
        return await conn.fetchrow(
            """
            update core.complaints
            set status = 'submitted', submitted_at = now()
            where id = $1 and user_id = $2 and status = 'draft'
            returning *
            """,
            complaint_id,
            user_id,
        )

    async def add_documents(
        self,
        conn: asyncpg.Connection,
        *,
        complaint_id: UUID,
        user_id: UUID,
        document_ids: list[UUID],
    ) -> int:
        if not document_ids:
            return 0
        result = await conn.execute(
            """
            insert into core.complaint_documents (complaint_id, document_id)
            select $1, d.id
            from core.documents d
            where d.id = any($2::uuid[]) and d.user_id = $3 and d.deleted_at is null
            on conflict do nothing
            """,
            complaint_id,
            document_ids,
            user_id,
        )
        try:
            return int(result.split()[-1])
        except (ValueError, IndexError):
            return 0

    async def list_documents(
        self, conn: asyncpg.Connection, complaint_id: UUID
    ) -> list[asyncpg.Record]:
        return list(
            await conn.fetch(
                """
                select d.id, d.type, d.status, d.original_filename, d.mime_type,
                       d.size_bytes, d.page_count, d.sha256, d.created_at
                from core.complaint_documents cd
                join core.documents d on d.id = cd.document_id
                where cd.complaint_id = $1 and d.deleted_at is null
                order by cd.created_at
                """,
                complaint_id,
            )
        )

    async def open_complaint_for_user(
        self, conn: asyncpg.Connection, user_id: UUID
    ) -> asyncpg.Record | None:
        return await conn.fetchrow(
            """
            select * from core.complaints
            where user_id = $1 and status not in ('resolved', 'closed')
            order by created_at desc
            limit 1
            """,
            user_id,
        )

    async def add_note(
        self,
        conn: asyncpg.Connection,
        *,
        complaint_id: UUID,
        author_id: UUID,
        body: str,
        is_internal: bool = True,
    ) -> asyncpg.Record:
        return await conn.fetchrow(
            """
            insert into core.case_notes (complaint_id, author_id, body, is_internal)
            values ($1, $2, $3, $4)
            returning *
            """,
            complaint_id,
            author_id,
            body,
            is_internal,
        )

    async def list_notes(
        self, conn: asyncpg.Connection, complaint_id: UUID
    ) -> list[asyncpg.Record]:
        return list(
            await conn.fetch(
                """
                select n.*, u.full_name as author_name
                from core.case_notes n
                left join core.users u on u.id = n.author_id
                where n.complaint_id = $1
                order by n.created_at asc
                """,
                complaint_id,
            )
        )

    async def open_by_tier(self, conn: asyncpg.Connection) -> list[asyncpg.Record]:
        return list(
            await conn.fetch(
                """
                select triage_tier, count(*) as count
                from core.complaints
                where status not in ('resolved', 'closed')
                group by triage_tier
                order by triage_tier
                """
            )
        )

    async def count_open(self, conn: asyncpg.Connection) -> int:
        return int(
            await conn.fetchval(
                """
                select count(*) from core.complaints
                where status not in ('resolved', 'closed')
                """
            )
            or 0
        )

    async def count_since(self, conn: asyncpg.Connection, since: datetime) -> int:
        return int(
            await conn.fetchval(
                "select count(*) from core.complaints where created_at >= $1",
                since,
            )
            or 0
        )
