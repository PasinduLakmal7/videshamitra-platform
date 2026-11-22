"""Chat and speech proxies to ai-service. Core does not persist chat content."""

from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import Response, StreamingResponse

from app.api.dependencies import get_ai_client, get_current_user
from app.db.pool import acquire
from app.models.entities import CurrentUser
from app.schemas.chat import (
    ChatMessageCreate,
    ChatSessionCreate,
    SpeechSynthesizeRequest,
)
from app.schemas.common import ok
from app.services.chat_service import ChatService
from app.utils.file_processing import validate_audio

router = APIRouter()


def _service(client) -> ChatService:  # type: ignore[no-untyped-def]
    return ChatService(client)


@router.post("/sessions", response_model=None, status_code=201)
async def create_session(
    payload: ChatSessionCreate,
    user: CurrentUser = Depends(get_current_user),
    client=Depends(get_ai_client),
):
    data = await _service(client).create_session(user, payload.model_dump(exclude_none=True))
    return ok(data)


@router.get("/sessions", response_model=None)
async def list_sessions(
    user: CurrentUser = Depends(get_current_user),
    client=Depends(get_ai_client),
):
    return ok(await _service(client).list_sessions(user))


@router.get("/sessions/{session_id}", response_model=None)
async def get_session(
    session_id: UUID,
    user: CurrentUser = Depends(get_current_user),
    client=Depends(get_ai_client),
):
    return ok(await _service(client).get_session(user, session_id))


@router.post("/sessions/{session_id}/messages")
async def send_message(
    session_id: UUID,
    payload: ChatMessageCreate,
    user: CurrentUser = Depends(get_current_user),
    client=Depends(get_ai_client),
):
    service = _service(client)
    await service.get_session(user, session_id)
    async with acquire() as conn:
        await service.check_attachments(conn, user, payload.attachments)

    async def event_stream() -> AsyncIterator[bytes]:
        async with client.stream_chat(
            str(session_id), str(user.id), payload.model_dump(mode="json", exclude_none=True)
        ) as upstream:
            async for chunk in upstream.aiter_raw():
                if chunk:
                    yield chunk

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.post("/transcribe", response_model=None)
async def transcribe(
    file: UploadFile = File(...),
    language: str | None = Form(default=None),
    user: CurrentUser = Depends(get_current_user),
    client=Depends(get_ai_client),
):
    from app.core.config import settings

    content = await file.read(settings.max_audio_bytes + 1)
    content, mime, filename = validate_audio(content, file.filename or "audio", file.content_type)
    body, content_type = await _service(client).transcribe(
        content=content, filename=filename, content_type=mime, language=language
    )
    if content_type.startswith("application/json"):
        import json

        return ok(json.loads(body))
    return Response(content=body, media_type=content_type)


@router.post("/synthesize")
async def synthesize(
    payload: SpeechSynthesizeRequest,
    user: CurrentUser = Depends(get_current_user),
    client=Depends(get_ai_client),
):
    body, content_type = await _service(client).synthesize(
        text=payload.text,
        language=payload.language,
        voice=payload.voice,
        audio_format=payload.format,
    )
    return Response(content=body, media_type=content_type)
