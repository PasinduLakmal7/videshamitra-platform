"""Chat/speech proxy service. No chat content is persisted in core."""

from __future__ import annotations

from typing import Any

from app.integrations.ai_client import AIClient
from app.models.entities import CurrentUser


class ChatService:
    def __init__(self, client: AIClient) -> None:
        self.client = client

    async def create_session(self, actor: CurrentUser, payload: dict[str, Any]) -> dict[str, Any]:
        return await self.client.create_chat_session(str(actor.id), payload)

    async def list_sessions(self, actor: CurrentUser) -> dict[str, Any]:
        return await self.client.list_chat_sessions(str(actor.id))

    async def get_session(self, actor: CurrentUser, session_id: str) -> dict[str, Any]:
        return await self.client.get_chat_session(session_id, str(actor.id))

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
