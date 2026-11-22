"""SQL for journeys and check-ins."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

import asyncpg

JOURNEY_SORT = {
    "created_at": "created_at",
    "next_checkin_at": "next_checkin_at",
    "departure_date": "departure_date",
}
CHECKIN_SORT = {
    "due_at": "due_at",
    "created_at": "created_at",
    "status": "status",
}


class MigrationRepository:
    async def create_journey(
        self,
        conn: asyncpg.Connection,
        *,
        user_id: UUID,
        agency_id: UUID | None,
        destination_country: str | None,
        employer_name: str | None,
        job_title: str | None,
        departure_date,
        return_date,
    ) -> asyncpg.Record:
        return await conn.fetchrow(
            """
            insert into core.migration_journeys
                (user_id, agency_id, destination_country, employer_name, job_title,
                 departure_date, return_date, stage)
            values ($1, $2, $3, $4, $5, $6, $7, 'pre_departure')
            returning *
            """,
            user_id,
            agency_id,
            destination_country,
            employer_name,
            job_title,
            departure_date,
            return_date,
        )

    async def get_journey(
        self, conn: asyncpg.Connection, journey_id: UUID
    ) -> asyncpg.Record | None:
        return await conn.fetchrow(
            """
            select j.*, a.name as agency_name
            from core.migration_journeys j
            left join core.agencies a on a.id = j.agency_id
            where j.id = $1
            """,
            journey_id,
        )

    async def active_journey_for_user(
        self, conn: asyncpg.Connection, user_id: UUID
    ) -> asyncpg.Record | None:
        return await conn.fetchrow(
            """
            select j.*, a.name as agency_name
            from core.migration_journeys j
            left join core.agencies a on a.id = j.agency_id
            where j.user_id = $1 and j.stage <> 'returned'
            order by j.created_at desc
            limit 1
            """,
            user_id,
        )

    async def list_journeys(
        self,
        conn: asyncpg.Connection,
        *,
        user_id: UUID | None,
        stage: str | None,
        page_size: int,
        offset: int,
        order_by: str,
    ) -> tuple[list[asyncpg.Record], int]:
        where = """
            where ($1::uuid is null or j.user_id = $1)
              and ($2::text is null or j.stage::text = $2)
        """
        params = [user_id, stage]
        total = await conn.fetchval(
            f"select count(*) from core.migration_journeys j {where}", *params
        )
        rows = await conn.fetch(
            f"""
            select j.*, a.name as agency_name
            from core.migration_journeys j
            left join core.agencies a on a.id = j.agency_id
            {where}
            order by {order_by}
            limit $3 offset $4
            """,
            *params,
            page_size,
            offset,
        )
        return list(rows), int(total or 0)

    async def update_journey(
        self, conn: asyncpg.Connection, journey_id: UUID, fields: dict[str, Any]
    ) -> asyncpg.Record | None:
        allowed = {
            "agency_id",
            "destination_country",
            "employer_name",
            "job_title",
            "departure_date",
            "return_date",
        }
        updates = {key: value for key, value in fields.items() if key in allowed}
        if not updates:
            return await self.get_journey(conn, journey_id)
        set_parts = []
        values: list[Any] = []
        for index, (column, value) in enumerate(updates.items(), start=1):
            set_parts.append(f"{column} = ${index}")
            values.append(value)
        values.append(journey_id)
        return await conn.fetchrow(
            f"""
            update core.migration_journeys
            set {", ".join(set_parts)}
            where id = ${len(values)}
            returning *
            """,
            *values,
        )

    async def set_consent(
        self, conn: asyncpg.Connection, journey_id: UUID, granted: bool
    ) -> asyncpg.Record | None:
        return await conn.fetchrow(
            """
            update core.migration_journeys
            set consent_checkins = $2,
                consent_at = case when $2 then now() else null end
            where id = $1
            returning *
            """,
            journey_id,
            granted,
        )

    async def set_stage(
        self, conn: asyncpg.Connection, journey_id: UUID, stage: str
    ) -> asyncpg.Record | None:
        return await conn.fetchrow(
            """
            update core.migration_journeys
            set stage = $2::core.journey_stage
            where id = $1
            returning *
            """,
            journey_id,
            stage,
        )

    async def refresh_next_checkin(self, conn: asyncpg.Connection, journey_id: UUID) -> None:
        await conn.execute(
            """
            update core.migration_journeys j
            set next_checkin_at = (
                select min(c.due_at)
                from core.checkins c
                where c.journey_id = j.id and c.status in ('scheduled', 'sent')
            )
            where j.id = $1
            """,
            journey_id,
        )

    # --- check-ins ------------------------------------------------------
    async def create_checkin(
        self,
        conn: asyncpg.Connection,
        *,
        journey_id: UUID,
        user_id: UUID,
        due_at: datetime,
        channel: str = "in_app",
    ) -> asyncpg.Record | None:
        return await conn.fetchrow(
            """
            insert into core.checkins (journey_id, user_id, due_at, channel, status)
            values ($1, $2, $3, $4::core.notification_channel, 'scheduled')
            on conflict (journey_id, due_at) do nothing
            returning *
            """,
            journey_id,
            user_id,
            due_at,
            channel,
        )

    async def get_checkin(
        self, conn: asyncpg.Connection, checkin_id: UUID
    ) -> asyncpg.Record | None:
        return await conn.fetchrow(
            """
            select c.*, j.stage, j.agency_id, j.destination_country, j.employer_name,
                   j.job_title, j.departure_date
            from core.checkins c
            join core.migration_journeys j on j.id = c.journey_id
            where c.id = $1
            """,
            checkin_id,
        )

    async def list_checkins(
        self,
        conn: asyncpg.Connection,
        *,
        user_id: UUID | None,
        journey_id: UUID | None,
        status: str | None,
        overdue_only: bool,
        page_size: int,
        offset: int,
        order_by: str,
    ) -> tuple[list[asyncpg.Record], int]:
        where = """
            where ($1::uuid is null or c.user_id = $1)
              and ($2::uuid is null or c.journey_id = $2)
              and ($3::text is null or c.status::text = $3)
              and (not $4::boolean or (c.due_at < now() and c.status in ('scheduled', 'sent')))
        """
        params = [user_id, journey_id, status, overdue_only]
        total = await conn.fetchval(f"select count(*) from core.checkins c {where}", *params)
        rows = await conn.fetch(
            f"""
            select c.*, j.stage, j.agency_id, j.destination_country, j.employer_name,
                   j.job_title
            from core.checkins c
            join core.migration_journeys j on j.id = c.journey_id
            {where}
            order by {order_by}
            limit $5 offset $6
            """,
            *params,
            page_size,
            offset,
        )
        return list(rows), int(total or 0)

    async def update_checkin(
        self, conn: asyncpg.Connection, checkin_id: UUID, fields: dict[str, Any]
    ) -> asyncpg.Record | None:
        allowed = {"due_at", "channel", "status"}
        updates = {key: value for key, value in fields.items() if key in allowed}
        if not updates:
            return await self.get_checkin(conn, checkin_id)
        set_parts = []
        values: list[Any] = []
        for index, (column, value) in enumerate(updates.items(), start=1):
            cast = ""
            if column == "channel":
                cast = "::core.notification_channel"
            elif column == "status":
                cast = "::core.checkin_status"
            set_parts.append(f"{column} = ${index}{cast}")
            values.append(value)
        values.append(checkin_id)
        return await conn.fetchrow(
            f"""
            update core.checkins
            set {", ".join(set_parts)}
            where id = ${len(values)}
            returning *
            """,
            *values,
        )

    async def respond(
        self,
        conn: asyncpg.Connection,
        *,
        checkin_id: UUID,
        user_id: UUID,
        response: dict[str, Any],
        risk_level: str | None,
    ) -> asyncpg.Record | None:
        return await conn.fetchrow(
            """
            update core.checkins
            set status = 'completed',
                completed_at = now(),
                response = $3,
                risk_level = $4::core.risk_level
            where id = $1 and user_id = $2 and status in ('scheduled', 'sent')
            returning *
            """,
            checkin_id,
            user_id,
            response,
            risk_level,
        )

    async def mark_escalated(
        self, conn: asyncpg.Connection, checkin_id: UUID
    ) -> asyncpg.Record | None:
        return await conn.fetchrow(
            """
            update core.checkins set status = 'escalated'
            where id = $1
            returning *
            """,
            checkin_id,
        )

    async def due_checkins(self, conn: asyncpg.Connection, limit: int = 50) -> list[asyncpg.Record]:
        return list(
            await conn.fetch(
                """
                select c.*, j.agency_id, j.destination_country, u.preferred_language
                from core.checkins c
                join core.migration_journeys j on j.id = c.journey_id
                join core.users u on u.id = c.user_id
                where c.status = 'scheduled' and c.due_at <= now()
                order by c.due_at
                limit $1
                for update of c skip locked
                """,
                limit,
            )
        )

    async def missed_checkins(
        self, conn: asyncpg.Connection, *, grace_hours: int, limit: int = 50
    ) -> list[asyncpg.Record]:
        return list(
            await conn.fetch(
                """
                select c.*, j.agency_id, u.preferred_language
                from core.checkins c
                join core.migration_journeys j on j.id = c.journey_id
                join core.users u on u.id = c.user_id
                where c.status in ('scheduled', 'sent')
                  and c.due_at <= now() - make_interval(hours => $1)
                order by c.due_at
                limit $2
                for update of c skip locked
                """,
                grace_hours,
                limit,
            )
        )

    async def mark_sent(self, conn: asyncpg.Connection, checkin_id: UUID) -> asyncpg.Record | None:
        return await conn.fetchrow(
            """
            update core.checkins
            set status = 'sent', sent_at = coalesce(sent_at, now())
            where id = $1 and status = 'scheduled'
            returning *
            """,
            checkin_id,
        )

    async def mark_missed(
        self, conn: asyncpg.Connection, checkin_id: UUID
    ) -> asyncpg.Record | None:
        return await conn.fetchrow(
            """
            update core.checkins set status = 'missed'
            where id = $1 and status in ('scheduled', 'sent')
            returning *
            """,
            checkin_id,
        )

    async def overdue_count(self, conn: asyncpg.Connection) -> int:
        return int(
            await conn.fetchval(
                """
                select count(*) from core.checkins
                where due_at < now() and status in ('scheduled', 'sent')
                """
            )
            or 0
        )

    async def checkins_for_journey(
        self, conn: asyncpg.Connection, journey_id: UUID
    ) -> list[asyncpg.Record]:
        return list(
            await conn.fetch(
                "select * from core.checkins where journey_id = $1 order by due_at",
                journey_id,
            )
        )
