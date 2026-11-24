"""Provider-neutral LLM interface. Every model call goes through an LLMClient."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, TypeVar
from uuid import UUID

from pydantic import BaseModel

from app.core.config import settings
from app.core.errors import AppError
from app.guardrails.pii import redact

T = TypeVar("T", bound=BaseModel)


@dataclass(frozen=True)
class BytesPart:
    data: bytes
    mime_type: str


Part = str | BytesPart


class ModelTier(StrEnum):
    FAST = "fast"  # classification, normalisation
    PRO = "pro"  # multi-page contract analysis


def model_for(tier: ModelTier) -> str:
    return settings.GEMINI_MODEL_PRO if tier is ModelTier.PRO else settings.GEMINI_MODEL_FAST


@dataclass(frozen=True)
class Usage:
    model: str
    tokens_in: int
    tokens_out: int

    @property
    def total(self) -> int:
        return self.tokens_in + self.tokens_out


@dataclass(frozen=True)
class CallMeta:
    purpose: str
    run_id: UUID | None = None


class LLMUnavailable(AppError):
    status_code = 503
    code = "llm_unavailable"


class LLMRejected(AppError):
    status_code = 502
    code = "llm_rejected"


class LLMInvalidOutput(AppError):
    status_code = 502
    code = "llm_invalid_output"


class BudgetExceeded(AppError):
    status_code = 429
    code = "budget_exceeded"


def redact_parts(parts: list[Part]) -> list[Part]:
    # PII hook: text never leaves the service unredacted. Bytes parts are documents (Phase 5).
    return [redact(part) if isinstance(part, str) else part for part in parts]


class LLMClient(Protocol):
    async def generate_json(
        self,
        parts: list[Part],
        schema: type[T],
        *,
        tier: ModelTier = ModelTier.FAST,
        system: str | None = None,
        timeout: float | None = None,
        meta: CallMeta | None = None,
    ) -> tuple[T, Usage]: ...

    async def generate_text(
        self,
        parts: list[Part],
        *,
        tier: ModelTier = ModelTier.FAST,
        system: str | None = None,
        timeout: float | None = None,
        meta: CallMeta | None = None,
    ) -> tuple[str, Usage]: ...

    async def transcribe(
        self,
        audio: bytes,
        mime_type: str,
        language: str | None = None,
        *,
        meta: CallMeta | None = None,
    ) -> tuple[str, Usage]: ...
