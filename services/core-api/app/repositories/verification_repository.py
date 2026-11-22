"""SQL for verification records and state transitions."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import asyncpg

SORT_COLUMNS = {
    "created_at": "created_at",
    "updated_at": "updated_at",
    "risk_score": "risk_score",
    "status": "status",
}

RESULT_STATUSES = ("verified", "suspicious", "fraudulent")


class VerificationRepository:
    async def create(
        self,
        conn: asyncpg.Connection,
        *,
        user_id: UUID,
        agency_id: UUID | None,
        agency_name_input: str | None,
        job_title: str | None,
        employer_name: str | None,
        destination_country: str | None,
        offered_salary: float | None,
        currency: str | None,
    ) -> asyncpg.Record:
        return await conn.fetchrow(
            """
            insert into core.verifications
                (user_id, agency_id, agency_name_input, job_title, employer_name,
                 destination_country, offered_salary, currency, status)
            values ($1, $2, $3, $4, $5, $6, $7, $8, 'pending')
            returning *
            """,
            user_id,
            agency_id,
            agency_name_input,
            job_title,
            employer_name,
            destination_country,
            offered_salary,
            currency,
        )

    async def get(self, conn: asyncpg.Connection, verification_id: UUID) -> asyncpg.Record | None:
        return await conn.fetchrow(
            """
            select v.*, a.name as agency_name, a.registration_no as agency_registration_no
            from core.verifications v
            left join core.agencies a on a.id = v.agency_id
            where v.id = $1
            """,
            verification_id,
        )

    async def list_verifications(
        self,
        conn: asyncpg.Connection,
        *,
        user_id: UUID | None,
        status: str | None,
        risk_level: str | None,
        agency_id: UUID | None,
        q: str | None,
        page_size: int,
        offset: int,
        order_by: str,
    ) -> tuple[list[asyncpg.Record], int]:
        where = """
            where ($1::uuid is null or v.user_id = $1)
              and ($2::text is null or v.status::text = $2)
              and ($3::text is null or v.risk_level::text = $3)
              and ($4::uuid is null or v.agency_id = $4)
              and ($5::text is null or v.job_title ilike '%' || $5 || '%'
                   or v.employer_name ilike '%' || $5 || '%'
                   or v.agency_name_input ilike '%' || $5 || '%')
        """
        params = [user_id, status, risk_level, agency_id, q]
        total = await conn.fetchval(f"select count(*) from core.verifications v {where}", *params)
        rows = await conn.fetch(
            f"""
            select v.*, a.name as agency_name, a.registration_no as agency_registration_no
            from core.verifications v
            left join core.agencies a on a.id = v.agency_id
            {where}
            order by {order_by}
            limit $6 offset $7
            """,
            *params,
            page_size,
            offset,
        )
        return list(rows), int(total or 0)

    async def apply_result(
        self,
        conn: asyncpg.Connection,
        *,
        verification_id: UUID,
        status: str,
        risk_level: str,
        risk_score: int | None,
        findings: list[dict[str, Any]],
        evidence: list[dict[str, Any]],
        engine_version: str | None,
        analysis_run_id: str | None,
    ) -> asyncpg.Record | None:
        return await conn.fetchrow(
            """
            update core.verifications
            set status = $2::core.verification_status,
                risk_level = $3::core.risk_level,
                risk_score = $4,
                findings = $5,
                evidence = $6,
                engine_version = $7,
                analysis_run_id = $8,
                failure_code = null,
                failure_message = null,
                completed_at = now()
            where id = $1 and status in ('pending', 'processing')
            returning *
            """,
            verification_id,
            status,
            risk_level,
            risk_score,
            findings,
            evidence,
            engine_version,
            analysis_run_id,
        )

    async def apply_failure(
        self,
        conn: asyncpg.Connection,
        *,
        verification_id: UUID,
        error_code: str,
        message: str,
    ) -> asyncpg.Record | None:
        return await conn.fetchrow(
            """
            update core.verifications
            set status = 'failed',
                failure_code = $2,
                failure_message = $3,
                completed_at = now()
            where id = $1 and status in ('pending', 'processing')
            returning *
            """,
            verification_id,
            error_code,
            message[:2000],
        )

    async def mark_retry(
        self, conn: asyncpg.Connection, verification_id: UUID
    ) -> asyncpg.Record | None:
        return await conn.fetchrow(
            """
            update core.verifications
            set status = 'pending',
                retry_count = retry_count + 1,
                failure_code = null,
                failure_message = null,
                completed_at = null,
                risk_level = null,
                risk_score = null,
                findings = '[]'::jsonb,
                evidence = '[]'::jsonb
            where id = $1
            returning *
            """,
            verification_id,
        )

    async def review(
        self,
        conn: asyncpg.Connection,
        *,
        verification_id: UUID,
        status: str,
        risk_level: str | None,
        risk_score: int | None,
        findings: list[dict[str, Any]] | None,
        reviewed_by: UUID,
    ) -> asyncpg.Record | None:
        return await conn.fetchrow(
            """
            update core.verifications
            set status = $2::core.verification_status,
                risk_level = coalesce($3::core.risk_level, risk_level),
                risk_score = coalesce($4, risk_score),
                findings = coalesce($5, findings),
                reviewed_by = $6,
                reviewed_at = now(),
                completed_at = coalesce(completed_at, now())
            where id = $1
            returning *
            """,
            verification_id,
            status,
            risk_level,
            risk_score,
            findings,
            reviewed_by,
        )

    async def stale_in_flight(
        self, conn: asyncpg.Connection, *, minutes: int, limit: int = 50
    ) -> list[asyncpg.Record]:
        cutoff = datetime.now(UTC) - timedelta(minutes=minutes)
        return list(
            await conn.fetch(
                """
                select * from core.verifications
                where status in ('pending', 'processing') and updated_at < $1
                order by updated_at
                limit $2
                """,
                cutoff,
                limit,
            )
        )
