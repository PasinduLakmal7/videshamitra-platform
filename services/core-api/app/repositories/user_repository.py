"""SQL for users and consent history."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import asyncpg

from app.models.enums import ConsentType, LanguageCode, UserRole

SORT_COLUMNS = {
    "created_at": "created_at",
    "full_name": "full_name",
    "role": "role",
}


class UserRepository:
    async def get_by_id(self, conn: asyncpg.Connection, user_id: UUID) -> asyncpg.Record | None:
        return await conn.fetchrow(
            """
            select id, role, full_name, phone, preferred_language, country_of_work,
                   is_active, created_at, updated_at
            from core.users
            where id = $1
            """,
            user_id,
        )

    async def get_by_phone(self, conn: asyncpg.Connection, phone: str) -> asyncpg.Record | None:
        return await conn.fetchrow(
            """
            select id, role, full_name, phone, preferred_language, country_of_work,
                   is_active, created_at, updated_at
            from core.users
            where phone = $1
            order by created_at
            limit 1
            """,
            phone,
        )

    async def ensure_from_claims(
        self, conn: asyncpg.Connection, user_id: UUID, claims: dict[str, Any]
    ) -> asyncpg.Record:
        meta = claims.get("user_metadata") or {}
        language = meta.get("preferred_language")
        if language not in {item.value for item in LanguageCode}:
            language = LanguageCode.EN.value
        await conn.execute(
            """
            insert into core.users (id, full_name, phone, preferred_language, country_of_work)
            values ($1, $2, $3, $4::core.language_code, $5)
            on conflict (id) do nothing
            """,
            user_id,
            meta.get("full_name"),
            claims.get("phone"),
            language,
            meta.get("country_of_work"),
        )
        row = await self.get_by_id(conn, user_id)
        if row is None:
            raise asyncpg.ForeignKeyViolationError("auth user does not exist")
        return row

    async def list_users(
        self,
        conn: asyncpg.Connection,
        *,
        page: int,
        page_size: int,
        offset: int,
        order_by: str,
        role: str | None = None,
        q: str | None = None,
        is_active: bool | None = None,
    ) -> tuple[list[asyncpg.Record], int]:
        where = """
            where ($1::text is null or role::text = $1)
              and ($2::text is null or full_name ilike '%' || $2 || '%'
                   or phone ilike '%' || $2 || '%')
              and ($3::boolean is null or is_active = $3)
        """
        params = [role, q, is_active]
        total = await conn.fetchval(f"select count(*) from core.users {where}", *params)
        rows = await conn.fetch(
            f"""
            select id, role, full_name, phone, preferred_language, country_of_work,
                   is_active, created_at, updated_at
            from core.users
            {where}
            order by {order_by}
            limit $4 offset $5
            """,
            *params,
            page_size,
            offset,
        )
        return list(rows), int(total or 0)

    async def update_profile(
        self, conn: asyncpg.Connection, user_id: UUID, fields: dict[str, Any]
    ) -> asyncpg.Record | None:
        allowed = {
            "full_name",
            "phone",
            "preferred_language",
            "country_of_work",
        }
        updates = {key: value for key, value in fields.items() if key in allowed}
        if not updates:
            return await self.get_by_id(conn, user_id)
        set_parts = []
        values: list[Any] = []
        for index, (column, value) in enumerate(updates.items(), start=1):
            cast = "::core.language_code" if column == "preferred_language" else ""
            set_parts.append(f"{column} = ${index}{cast}")
            values.append(value)
        values.append(user_id)
        return await conn.fetchrow(
            f"""
            update core.users
            set {", ".join(set_parts)}
            where id = ${len(values)}
            returning id, role, full_name, phone, preferred_language, country_of_work,
                      is_active, created_at, updated_at
            """,
            *values,
        )

    async def set_role(
        self, conn: asyncpg.Connection, user_id: UUID, role: UserRole | str
    ) -> asyncpg.Record | None:
        return await conn.fetchrow(
            """
            update core.users set role = $2::core.user_role
            where id = $1
            returning id, role, full_name, phone, preferred_language, country_of_work,
                      is_active, created_at, updated_at
            """,
            user_id,
            str(role),
        )

    async def set_active(
        self, conn: asyncpg.Connection, user_id: UUID, is_active: bool
    ) -> asyncpg.Record | None:
        return await conn.fetchrow(
            """
            update core.users set is_active = $2
            where id = $1
            returning id, role, full_name, phone, preferred_language, country_of_work,
                      is_active, created_at, updated_at
            """,
            user_id,
            is_active,
        )

    async def list_consents(self, conn: asyncpg.Connection, user_id: UUID) -> list[asyncpg.Record]:
        return list(
            await conn.fetch(
                """
                select id, user_id, type, granted, version, granted_at, revoked_at,
                       ip_address::text as ip_address, user_agent, created_at
                from core.user_consents
                where user_id = $1
                order by created_at desc
                """,
                user_id,
            )
        )

    async def latest_consent(
        self, conn: asyncpg.Connection, user_id: UUID, consent_type: ConsentType
    ) -> asyncpg.Record | None:
        return await conn.fetchrow(
            """
            select id, user_id, type, granted, version, granted_at, revoked_at,
                   ip_address::text as ip_address, user_agent, created_at
            from core.user_consents
            where user_id = $1 and type = $2::core.consent_type
            order by created_at desc
            limit 1
            """,
            user_id,
            consent_type.value,
        )

    async def create_consent(
        self,
        conn: asyncpg.Connection,
        *,
        user_id: UUID,
        consent_type: ConsentType,
        granted: bool,
        version: str,
        ip_address: str | None,
        user_agent: str | None,
    ) -> asyncpg.Record:
        return await conn.fetchrow(
            """
            insert into core.user_consents
                (user_id, type, granted, version, granted_at, revoked_at, ip_address, user_agent)
            values (
                $1, $2::core.consent_type, $3, $4,
                case when $3 then now() else null end,
                case when $3 then null else now() end,
                $5::inet, $6
            )
            returning id, user_id, type, granted, version, granted_at, revoked_at,
                      ip_address::text as ip_address, user_agent, created_at
            """,
            user_id,
            consent_type.value,
            granted,
            version,
            ip_address,
            user_agent,
        )
