"""Chat/speech proxy service. No chat content is persisted in core."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import asyncpg

from app.core.exceptions import NotFound
from app.integrations.ai_client import AIClient
from app.models.entities import CurrentUser
from app.repositories.document_repository import DocumentRepository


class ChatService:
    def __init__(self, client: AIClient, documents: DocumentRepository | None = None) -> None:
        self.client = client
        self.documents = documents or DocumentRepository()

    async def check_attachments(
        self, conn: asyncpg.Connection, actor: CurrentUser, attachments: list[UUID]
    ) -> None:
        if not attachments:
            return
        wanted = set(attachments)
        owned = await self.documents.owned_ids(conn, user_id=actor.id, document_ids=list(wanted))
        if owned != wanted:
            raise NotFound("One or more attachments were not found", code="attachment_not_found")

    async def create_session(self, actor: CurrentUser, payload: dict[str, Any]) -> dict[str, Any]:
        return await self.client.create_chat_session(str(actor.id), payload)

    async def list_sessions(self, actor: CurrentUser) -> dict[str, Any]:
        return await self.client.list_chat_sessions(str(actor.id))

    async def get_session(self, actor: CurrentUser, session_id: UUID) -> dict[str, Any]:
        return await self.client.get_chat_session(str(session_id), str(actor.id))

    async def transcribe(
        self,
        *,
        content: bytes,
        filename: str,
        content_type: str,
        language: str | None,
    ) -> tuple[bytes, str]:
        return await self.client.transcribe(
            content=content,
            filename=filename,
            content_type=content_type,
            language=language,
        )

    async def synthesize(
        self,
        *,
        text: str,
        language: str | None,
        voice: str | None,
        audio_format: str,
    ) -> tuple[bytes, str]:
        return await self.client.synthesize(
            text=text, language=language, voice=voice, audio_format=audio_format
        )
