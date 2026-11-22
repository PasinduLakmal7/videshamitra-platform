"""SQL for the append-only audit log."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import asyncpg


class AuditRepository:
    async def record(
        self,
        conn: asyncpg.Connection,
        *,
        actor_id: UUID | None,
        actor_role: str | None,
        action: str,
        entity_type: str | None,
        entity_id: UUID | None,
        ip_address: str | None,
        user_agent: str | None,
        metadata: dict[str, Any],
    ) -> asyncpg.Record:
        return await conn.fetchrow(
            """
            insert into core.audit_logs
                (actor_id, actor_role, action, entity_type, entity_id,
                 ip_address, user_agent, metadata)
            values ($1, $2::core.user_role, $3, $4, $5, $6::inet, $7, $8)
            returning *
            """,
            actor_id,
            actor_role,
            action,
            entity_type,
            entity_id,
            ip_address,
            user_agent,
            metadata,
        )

    async def list_logs(
        self,
        conn: asyncpg.Connection,
        *,
        actor_id: UUID | None,
        action: str | None,
        entity_type: str | None,
        entity_id: UUID | None,
        page_size: int,
        offset: int,
    ) -> tuple[list[asyncpg.Record], int]:
        where = """
            where ($1::uuid is null or actor_id = $1)
              and ($2::text is null or action = $2)
              and ($3::text is null or entity_type = $3)
              and ($4::uuid is null or entity_id = $4)
        """
        params = [actor_id, action, entity_type, entity_id]
        total = await conn.fetchval(f"select count(*) from core.audit_logs {where}", *params)
        rows = await conn.fetch(
            f"""
            select id, actor_id, actor_role, action, entity_type, entity_id,
                   ip_address::text as ip_address, user_agent, metadata, created_at
            from core.audit_logs
            {where}
            order by created_at desc
            limit $5 offset $6
            """,
            *params,
            page_size,
            offset,
        )
        return list(rows), int(total or 0)
