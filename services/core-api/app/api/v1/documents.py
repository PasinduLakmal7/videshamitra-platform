"""Document upload/download/delete and staff reprocess."""

from __future__ import annotations

import json
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile, status
from fastapi.responses import JSONResponse

from app.api.dependencies import (
    get_current_user,
    get_idempotency_key,
    get_request_info,
    get_storage,
    staff_user,
)
from app.core.config import settings
from app.core.idempotency import (
    abort_idempotency,
    begin_idempotency,
    complete_idempotency,
)
from app.db.pool import get_connection
from app.models.entities import CurrentUser, RequestInfo
from app.models.enums import DocumentType
from app.repositories.document_repository import SORT_COLUMNS
from app.schemas.common import ApiResponse, MessageData, PageParams, PageResponse, ok, page_data
from app.schemas.document import DocumentOut, DownloadUrlOut
from app.services.document_service import DocumentService
from app.utils.hashing import sha256_bytes

router = APIRouter()


@router.post(
    "",
    response_model=ApiResponse[DocumentOut],
    status_code=status.HTTP_201_CREATED,
    summary="Upload a document (multipart, Idempotency-Key required)",
)
async def upload_document(
    request: Request,
    file: UploadFile = File(...),
    document_type: DocumentType = Form(...),
    metadata: str | None = Form(default=None),
    idem_key: str | None = Depends(get_idempotency_key),
    user: CurrentUser = Depends(get_current_user),
    conn: asyncpg.Connection = Depends(get_connection),
    request_info: RequestInfo = Depends(get_request_info),
    storage=Depends(get_storage),
):
    content = await file.read(settings.max_upload_bytes + 1)
    parsed_metadata = {}
    if metadata:
        try:
            parsed_metadata = json.loads(metadata)
        except json.JSONDecodeError as exc:
            from app.core.exceptions import BadRequest

            raise BadRequest("metadata must be valid JSON", code="invalid_metadata") from exc

    ctx = await begin_idempotency(
        conn,
        user_id=user.id,
        key=idem_key,
        method="POST",
        path=request.url.path,
        payload={
            "sha256": sha256_bytes(content),
            "type": document_type.value,
            "filename": file.filename,
        },
    )
    if not ctx.acquired:
        return JSONResponse(status_code=ctx.status_code, content=ok(ctx.replay))
    try:
        row = await DocumentService(storage=storage).upload(
            conn,
            actor=user,
            content=content,
            filename=file.filename or "document",
            content_type=file.content_type,
            document_type=document_type.value,
            metadata=parsed_metadata,
            request=request_info,
        )
    except Exception:
        await abort_idempotency(conn, ctx)
        raise
    data = DocumentOut.from_record(row).model_dump(mode="json")
    await complete_idempotency(conn, ctx, data, status_code=201)
    return JSONResponse(status_code=201, content=ok(data))


@router.get("", response_model=PageResponse[DocumentOut])
async def list_documents(
    params: PageParams = Depends(),
    verification_id: UUID | None = Query(default=None),
    document_type: DocumentType | None = Query(default=None),
    user: CurrentUser = Depends(get_current_user),
    conn: asyncpg.Connection = Depends(get_connection),
    storage=Depends(get_storage),
):
    order_by = params.resolve_sort(SORT_COLUMNS, "created_at")
    rows, total = await DocumentService(storage=storage).list_documents(
        conn,
        actor=user,
        verification_id=verification_id,
        document_type=document_type.value if document_type else None,
        page_size=params.page_size,
        offset=params.offset,
        order_by=order_by,
    )
    return page_data([DocumentOut.from_record(row) for row in rows], total, params)


@router.get("/{document_id}", response_model=ApiResponse[DocumentOut])
async def get_document(
    document_id: UUID,
    user: CurrentUser = Depends(get_current_user),
    conn: asyncpg.Connection = Depends(get_connection),
    storage=Depends(get_storage),
):
    row = await DocumentService(storage=storage).get(conn, actor=user, document_id=document_id)
    return ok(DocumentOut.from_record(row))


@router.get("/{document_id}/download-url", response_model=ApiResponse[DownloadUrlOut])
async def get_download_url(
    document_id: UUID,
    user: CurrentUser = Depends(get_current_user),
    conn: asyncpg.Connection = Depends(get_connection),
    request_info: RequestInfo = Depends(get_request_info),
    storage=Depends(get_storage),
):
    url, expires_in = await DocumentService(storage=storage).download_url(
        conn, actor=user, document_id=document_id, request=request_info
    )
    return ok(DownloadUrlOut(url=url, expires_in=expires_in))


@router.delete("/{document_id}", response_model=ApiResponse[MessageData])
async def delete_document(
    document_id: UUID,
    user: CurrentUser = Depends(get_current_user),
    conn: asyncpg.Connection = Depends(get_connection),
    request_info: RequestInfo = Depends(get_request_info),
    storage=Depends(get_storage),
):
    await DocumentService(storage=storage).delete(
        conn, actor=user, document_id=document_id, request=request_info
    )
    return ok(MessageData(message="Document deleted").model_dump())


@router.post("/{document_id}/reprocess", response_model=ApiResponse[DocumentOut])
async def reprocess_document(
    document_id: UUID,
    user: CurrentUser = Depends(staff_user),
    conn: asyncpg.Connection = Depends(get_connection),
    request_info: RequestInfo = Depends(get_request_info),
    storage=Depends(get_storage),
):
    row = await DocumentService(storage=storage).reprocess(
        conn, actor=user, document_id=document_id, request=request_info
    )
    return ok(DocumentOut.from_record(row))
