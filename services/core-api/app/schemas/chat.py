"""Chat/speech DTOs (proxied to ai-service)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class ChatSessionCreate(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    language: str | None = Field(default=None, max_length=8)
    context: dict[str, Any] = Field(default_factory=dict)


class ChatMessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=8000)
    attachments: list[UUID] = Field(default_factory=list, max_length=10)
    language: str | None = Field(default=None, max_length=8)


class SpeechSynthesizeRequest(BaseModel):
    text: str = Field(min_length=1, max_length=5000)
    language: str | None = Field(default=None, max_length=8)
    voice: str | None = Field(default=None, max_length=50)
    format: str = Field(default="mp3", pattern="^(mp3|wav|ogg)$")
