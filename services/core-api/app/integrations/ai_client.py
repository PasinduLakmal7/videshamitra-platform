"""Client for ai-service internal endpoints (chat, speech, traces, webhooks)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import httpx

from app.integrations.base import BaseServiceClient


class AIClient(BaseServiceClient):
    def __init__(
        self,
        base_url: str,
        *,
        timeout: float | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(
            base_url,
            service_name="ai-service",
            audience="ai-service",
            timeout=timeout,
            client=client,
        )

    async def create_chat_session(self, user_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        response = await self.request(
            "POST",
            "/internal/v1/chat/sessions",
            json={"user_id": user_id, **payload},
        )
        return response.json()

    async def list_chat_sessions(self, user_id: str) -> dict[str, Any]:
        response = await self.request(
            "GET", "/internal/v1/chat/sessions", params={"user_id": user_id}
        )
        return response.json()

    async def get_chat_session(self, session_id: str, user_id: str) -> dict[str, Any]:
        response = await self.request(
            "GET",
            f"/internal/v1/chat/sessions/{session_id}",
            params={"user_id": user_id},
        )
        return response.json()

    @asynccontextmanager
    async def stream_chat(
        self, session_id: str, user_id: str, payload: dict[str, Any]
    ) -> AsyncIterator[httpx.Response]:
        headers = self.headers({"Accept": "text/event-stream"})
        try:
            async with self._client.stream(
                "POST",
                f"/internal/v1/chat/sessions/{session_id}/messages",
                json={"user_id": user_id, **payload},
                headers=headers,
                timeout=None,
            ) as response:
                self._raise_for_response(response)
                yield response
        except httpx.TimeoutException as exc:
            from app.core.exceptions import UpstreamError

            raise UpstreamError("ai-service stream timed out", service="ai-service") from exc
        except httpx.HTTPError as exc:
            from app.core.exceptions import UpstreamError

            raise UpstreamError("ai-service stream failed", service="ai-service") from exc

    async def transcribe(
        self,
        *,
        content: bytes,
        filename: str,
        content_type: str,
        language: str | None = None,
    ) -> tuple[bytes, str]:
        data = {"language": language} if language else None
        response = await self.request(
            "POST",
            "/internal/v1/speech/transcribe",
            files={"file": (filename, content, content_type)},
            data=data,
            timeout=60.0,
        )
        return response.content, response.headers.get("content-type", "application/json")

    async def synthesize(
        self,
        *,
        text: str,
        language: str | None = None,
        voice: str | None = None,
        audio_format: str = "mp3",
    ) -> tuple[bytes, str]:
        response = await self.request(
            "POST",
            "/internal/v1/speech/synthesize",
            json={"text": text, "language": language, "voice": voice, "format": audio_format},
            timeout=60.0,
        )
        return response.content, response.headers.get("content-type", "audio/mpeg")

    async def get_trace(self, verification_id: str) -> dict[str, Any]:
        response = await self.request("GET", f"/internal/v1/analyses/{verification_id}")
        return response.json()

    async def forward_whatsapp(
        self, payload: dict[str, Any], provider_message_id: str | None
    ) -> None:
        headers = {"X-Provider-Message-ID": provider_message_id} if provider_message_id else None
        await self.request(
            "POST",
            "/internal/v1/webhooks/whatsapp",
            json=payload,
            extra_headers=headers,
            timeout=30.0,
        )
