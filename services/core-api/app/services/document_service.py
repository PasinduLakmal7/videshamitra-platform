"""Document upload, validation, signed URLs and soft delete."""

from __future__ import annotations

import logging
from uuid import UUID, uuid4

import asyncpg

from app.core.config import settings
from app.core.exceptions import Conflict, Forbidden, NotFound
from app.core.permissions import is_admin, is_staff
from app.integrations.supabase.storage import SupabaseStorage
from app.models.entities import CurrentUser, RequestInfo
from app.repositories.document_repository import DocumentRepository
from app.schemas.document import DocumentOut
from app.services.audit_service import AuditService
from app.utils.file_processing import sanitize_filename, validate_document

logger = logging.getLogger(__name__)


class DocumentService:
    def __init__(
        self,
        repo: DocumentRepository | None = None,
        storage: SupabaseStorage | None = None,
        audit: AuditService | None = None,
    ) -> None:
        self.repo = repo or DocumentRepository()
        self.storage = storage or SupabaseStorage()
        self.audit = audit or AuditService()

    async def upload(
        self,
        conn: asyncpg.Connection,
        *,
        actor: CurrentUser,
        content: bytes,
        filename: str,
        content_type: str | None,
        document_type: str,
        metadata: dict | None = None,
        request: RequestInfo,
    ) -> asyncpg.Record:
        validated = validate_document(content, filename, content_type)
        duplicate = await self.repo.find_live_by_sha(conn, actor.id, validated.sha256)
        if duplicate is not None:
            raise Conflict(
                "This document has already been uploaded",
                code="duplicate_document",
                details={"document_id": str(duplicate["id"])},
            )

        count = await self.repo.count_for_user(conn, actor.id)
        if count >= 100:
            raise Conflict(
                "Document limit reached; delete an old document first",
                code="document_limit_reached",
            )

        document_id = uuid4()
        safe_name = sanitize_filename(validated.filename)
        path = f"{actor.id}/{document_id}/{safe_name}"
        await self.storage.upload(path, validated.content, validated.mime_type)
        try:
            row = await self.repo.create(
                conn,
                user_id=actor.id,
                document_type=document_type,
                storage_path=path,
                original_filename=(filename.rsplit("/", 1)[-1] or safe_name)[:255],
                mime_type=validated.mime_type,
                size_bytes=validated.size_bytes,
                page_count=validated.page_count,
                sha256=validated.sha256,
                metadata={
                    **(metadata or {}),
                    "pages": validated.page_count,
                    "detected_mime": validated.mime_type,
                },
            )
        except Exception:
            await self.storage.remove(path)
            raise

        await self.audit.record(
            conn,
            actor=actor,
            action="document.uploaded",
            entity_type="document",
            entity_id=row["id"],
            request=request,
            metadata={"type": document_type, "size_bytes": validated.size_bytes},
        )
        return row

    async def _get_authorised(
        self,
        conn: asyncpg.Connection,
        *,
        actor: CurrentUser,
        document_id: UUID,
        allow_deleted: bool = False,
    ) -> asyncpg.Record:
        row = await self.repo.get(conn, document_id, include_deleted=allow_deleted)
        if row is None:
            raise NotFound("Document not found")
        if row["user_id"] != actor.id and not is_staff(actor):
            raise Forbidden("You do not have access to this document")
        return row

    async def get(
        self, conn: asyncpg.Connection, *, actor: CurrentUser, document_id: UUID
    ) -> asyncpg.Record:
        return await self._get_authorised(conn, actor=actor, document_id=document_id)

    async def list_documents(
        self,
        conn: asyncpg.Connection,
        *,
        actor: CurrentUser,
        verification_id: UUID | None,
        document_type: str | None,
        page_size: int,
        offset: int,
        order_by: str,
    ):
        user_id = None if is_staff(actor) else actor.id
        return await self.repo.list_documents(
            conn,
            user_id=user_id,
            verification_id=verification_id,
            document_type=document_type,
            page_size=page_size,
            offset=offset,
            order_by=order_by,
        )

    async def download_url(
        self,
        conn: asyncpg.Connection,
        *,
        actor: CurrentUser,
        document_id: UUID,
        request: RequestInfo,
    ) -> tuple[str, int]:
        row = await self._get_authorised(conn, actor=actor, document_id=document_id)
        url = await self.storage.signed_url(row["storage_path"], settings.SIGNED_URL_TTL_SECONDS)
        await self.audit.record(
            conn,
            actor=actor,
            action="document.download_url_issued",
            entity_type="document",
            entity_id=document_id,
            request=request,
        )
        return url, settings.SIGNED_URL_TTL_SECONDS

    async def delete(
        self,
        conn: asyncpg.Connection,
        *,
        actor: CurrentUser,
        document_id: UUID,
        request: RequestInfo,
    ) -> None:
        row = await self.repo.get(conn, document_id)
        if row is None:
            raise NotFound("Document not found")
        if row["user_id"] != actor.id and not is_admin(actor):
            raise Forbidden("Only the owner or an admin can delete a document")
        deleted = await self.repo.soft_delete(conn, document_id, row["user_id"])
        if deleted is None:
            raise NotFound("Document not found")
        await self.storage.remove(row["storage_path"])
        await self.audit.record(
            conn,
            actor=actor,
            action="document.deleted",
            entity_type="document",
            entity_id=document_id,
            request=request,
        )

    async def get_bytes(
        self, conn: asyncpg.Connection, document_id: UUID
    ) -> tuple[asyncpg.Record, bytes]:
        row = await self.repo.get(conn, document_id)
        if row is None:
            raise NotFound("Document not found")
        if row["size_bytes"] > settings.max_upload_bytes:
            raise Forbidden("Document exceeds the internal download limit")
        content = await self.storage.download(row["storage_path"])
        return row, content

    async def reprocess(
        self,
        conn: asyncpg.Connection,
        *,
        actor: CurrentUser,
        document_id: UUID,
        request: RequestInfo,
    ) -> asyncpg.Record:
        if not is_staff(actor):
            raise Forbidden("Staff access required")
        row = await self.repo.get(conn, document_id)
        if row is None:
            raise NotFound("Document not found")
        await self.repo.update_status(conn, document_id, "uploaded")
        if row["verification_id"]:
            from app.services.verification_service import VerificationService

            await VerificationService().retry(
                conn,
                actor=actor,
                verification_id=row["verification_id"],
                request=request,
                force=True,
            )
        await self.audit.record(
            conn,
            actor=actor,
            action="document.reprocess_requested",
            entity_type="document",
            entity_id=document_id,
            request=request,
        )
        updated = await self.repo.get(conn, document_id)
        assert updated is not None
        return updated

    @staticmethod
    def to_out(row) -> DocumentOut:
        return DocumentOut.from_record(row)
