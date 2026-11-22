"""SQL for document metadata (blobs live in Supabase Storage)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import asyncpg

SORT_COLUMNS = {
    "created_at": "created_at",
    "original_filename": "original_filename",
    "size_bytes": "size_bytes",
    "type": "type",
}


class DocumentRepository:
    async def create(
        self,
        conn: asyncpg.Connection,
        *,
        user_id: UUID,
        document_type: str,
        storage_path: str,
        original_filename: str,
        mime_type: str,
        size_bytes: int,
        page_count: int | None,
        sha256: str,
        metadata: dict[str, Any],
    ) -> asyncpg.Record:
        return await conn.fetchrow(
            """
            insert into core.documents
                (user_id, type, status, storage_path, original_filename, mime_type,
                 size_bytes, page_count, sha256, metadata)
            values ($1, $2::core.document_type, 'uploaded', $3, $4, $5, $6, $7, $8, $9)
            returning *
            """,
            user_id,
            document_type,
            storage_path,
            original_filename,
            mime_type,
            size_bytes,
            page_count,
            sha256,
            metadata,
        )

    async def owned_ids(
        self, conn: asyncpg.Connection, *, user_id: UUID, document_ids: list[UUID]
    ) -> set[UUID]:
        rows = await conn.fetch(
            """
            select id from core.documents
            where id = any($1::uuid[]) and user_id = $2 and deleted_at is null
            """,
            document_ids,
            user_id,
        )
        return {row["id"] for row in rows}

    async def get(
        self,
        conn: asyncpg.Connection,
        document_id: UUID,
        *,
        include_deleted: bool = False,
    ) -> asyncpg.Record | None:
        clause = "" if include_deleted else "and deleted_at is null"
        return await conn.fetchrow(
            f"select * from core.documents where id = $1 {clause}",
            document_id,
        )

    async def find_live_by_sha(
        self, conn: asyncpg.Connection, user_id: UUID, sha256: str
    ) -> asyncpg.Record | None:
        return await conn.fetchrow(
            """
            select * from core.documents
            where user_id = $1 and sha256 = $2 and deleted_at is null
            limit 1
            """,
            user_id,
            sha256,
        )

    async def list_documents(
        self,
        conn: asyncpg.Connection,
        *,
        user_id: UUID | None,
        verification_id: UUID | None,
        document_type: str | None,
        page_size: int,
        offset: int,
        order_by: str,
        include_deleted: bool = False,
    ) -> tuple[list[asyncpg.Record], int]:
        where = """
            where ($1::uuid is null or user_id = $1)
              and ($2::uuid is null or verification_id = $2)
              and ($3::text is null or type::text = $3)
              and ($4::boolean or deleted_at is null)
        """
        params = [user_id, verification_id, document_type, include_deleted]
        total = await conn.fetchval(f"select count(*) from core.documents {where}", *params)
        rows = await conn.fetch(
            f"""
            select * from core.documents
            {where}
            order by {order_by}
            limit $5 offset $6
            """,
            *params,
            page_size,
            offset,
        )
        return list(rows), int(total or 0)

    async def soft_delete(
        self, conn: asyncpg.Connection, document_id: UUID, user_id: UUID
    ) -> asyncpg.Record | None:
        return await conn.fetchrow(
            """
            update core.documents
            set deleted_at = now()
            where id = $1 and user_id = $2 and deleted_at is null
            returning *
            """,
            document_id,
            user_id,
        )

    async def update_status(self, conn: asyncpg.Connection, document_id: UUID, status: str) -> None:
        await conn.execute(
            "update core.documents set status = $2::core.document_status where id = $1",
            document_id,
            status,
        )

    async def link_to_verification(
        self,
        conn: asyncpg.Connection,
        *,
        verification_id: UUID,
        user_id: UUID,
        document_ids: list[UUID],
    ) -> int:
        result = await conn.execute(
            """
            update core.documents
            set verification_id = $1, status = 'processing'
            where id = any($2::uuid[]) and user_id = $3 and deleted_at is null
            """,
            verification_id,
            document_ids,
            user_id,
        )
        try:
            return int(result.split()[-1])
        except (ValueError, IndexError):
            return 0

    async def count_for_user(self, conn: asyncpg.Connection, user_id: UUID) -> int:
        return int(
            await conn.fetchval(
                """
                select count(*) from core.documents
                where user_id = $1 and deleted_at is null
                """,
                user_id,
            )
            or 0
        )
