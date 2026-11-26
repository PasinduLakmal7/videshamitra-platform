"""Deterministic in-process LLM for tests. Responses are keyed on the redacted prompt."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, ValidationError

from app.llm.base import (
    BytesPart,
    CallMeta,
    LLMInvalidOutput,
    ModelTier,
    Part,
    T,
    Usage,
    model_for,
    redact_parts,
)

TEXT = "__text__"


def prompt_key(parts: list[Part], schema_name: str, tier: ModelTier) -> str:
    digest = hashlib.sha256()
    for part in redact_parts(parts):
        if isinstance(part, BytesPart):
            digest.update(part.mime_type.encode() + hashlib.sha256(part.data).digest())
        else:
            digest.update(part.encode())
        digest.update(b"\x00")
    digest.update(f"{schema_name}|{tier}".encode())
    return digest.hexdigest()


@dataclass
class FakeLLM:
    responses: dict[str, Any] = field(default_factory=dict)
    calls: list[dict[str, Any]] = field(default_factory=list)

    def register(
        self,
        parts: list[Part],
        value: Any,
        *,
        schema: type[BaseModel] | None = None,
        tier: ModelTier = ModelTier.FAST,
    ) -> None:
        name = schema.__name__ if schema else TEXT
        self.responses[prompt_key(parts, name, tier)] = value

    def _answer(
        self,
        parts: list[Part],
        name: str,
        tier: ModelTier,
        meta: CallMeta | None,
        system: str | None = None,
    ):
        sent = redact_parts(parts)
        self.calls.append(
            {"parts": sent, "schema": name, "tier": tier, "meta": meta, "system": system}
        )
        key = prompt_key(parts, name, tier)
        if key not in self.responses:
            raise LLMInvalidOutput("No fake response registered for this prompt")
        value = self.responses[key]
        if isinstance(value, Exception):
            raise value
        text_len = sum(len(p) for p in sent if isinstance(p, str))
        usage = Usage(model=model_for(tier), tokens_in=text_len // 4 + 1, tokens_out=8)
        return value, usage

    async def generate_json(
        self,
        parts: list[Part],
        schema: type[T],
        *,
        tier: ModelTier = ModelTier.FAST,
        system: str | None = None,
        timeout: float | None = None,
        meta: CallMeta | None = None,
    ) -> tuple[T, Usage]:
        value, usage = self._answer(parts, schema.__name__, tier, meta, system)
        try:
            return schema.model_validate(value), usage
        except ValidationError as exc:
            raise LLMInvalidOutput("Model output did not match the schema") from exc

    async def generate_text(
        self,
        parts: list[Part],
        *,
        tier: ModelTier = ModelTier.FAST,
        system: str | None = None,
        timeout: float | None = None,
        meta: CallMeta | None = None,
    ) -> tuple[str, Usage]:
        value, usage = self._answer(parts, TEXT, tier, meta, system)
        return str(value), usage

    async def transcribe(
        self,
        audio: bytes,
        mime_type: str,
        language: str | None = None,
        *,
        meta: CallMeta | None = None,
    ) -> tuple[str, Usage]:
        value, usage = self._answer([BytesPart(audio, mime_type)], TEXT, ModelTier.FAST, meta)
        return str(value), usage
