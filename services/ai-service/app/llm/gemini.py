"""Gemini provider (google-genai) with timeouts, bounded retries and typed JSON output."""

from __future__ import annotations

import asyncio
import logging
import random
from collections.abc import Awaitable, Callable
from typing import Any

import httpx
import httpx2
from google import genai
from google.genai import errors, types
from pydantic import ValidationError

from app.core.config import settings
from app.guardrails.pii import redact
from app.llm.base import (
    BytesPart,
    CallMeta,
    LLMInvalidOutput,
    LLMRejected,
    LLMUnavailable,
    ModelTier,
    Part,
    T,
    Usage,
    model_for,
    redact_parts,
)

logger = logging.getLogger(__name__)

RETRYABLE_STATUS = frozenset({408, 429, 500, 502, 503, 504})
BACKOFF_BASE_SECONDS = 0.5
BACKOFF_CAP_SECONDS = 8.0
MAX_ERROR_CHARS = 200
CONNECT_TIMEOUT_SECONDS = 5.0
TRANSIENT_ERRORS = (TimeoutError, httpx.TransportError, httpx2.TransportError)

SAFETY_SETTINGS = [
    types.SafetySetting(
        category=category, threshold=types.HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE
    )
    for category in (
        types.HarmCategory.HARM_CATEGORY_HARASSMENT,
        types.HarmCategory.HARM_CATEGORY_HATE_SPEECH,
        types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
        types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
    )
]

FAST_THINKING = types.ThinkingConfig(thinking_level=types.ThinkingLevel.LOW)

TRANSCRIBE_INSTRUCTION = (
    "Transcribe the speech in this audio verbatim. Return only the transcript text."
)
# Allowlist: the hint is interpolated into the prompt.
TRANSCRIBE_LANGUAGES = {"en": "English", "si": "Sinhala", "ta": "Tamil"}


class GeminiClient:
    def __init__(
        self,
        api_key: str | None = None,
        *,
        client: genai.Client | None = None,
        sleep: Callable[[float], Awaitable[Any]] = asyncio.sleep,
    ) -> None:
        self._api_key = api_key or settings.GEMINI_API_KEY.get_secret_value()
        self._http: httpx.AsyncClient | None = None
        if client is None:
            if not self._api_key:
                raise LLMUnavailable("GEMINI_API_KEY is not configured")
            # Own the transport: the SDK otherwise picks httpx or httpx2 at runtime.
            self._http = httpx.AsyncClient(
                timeout=httpx.Timeout(settings.LLM_TIMEOUT_SECONDS, connect=CONNECT_TIMEOUT_SECONDS)
            )
            client = genai.Client(
                api_key=self._api_key,
                http_options=types.HttpOptions(httpx_async_client=self._http),
            )
        self._client = client
        self._sleep = sleep

    async def aclose(self) -> None:
        if self._http is not None:
            await self._http.aclose()

    def _safe_message(self, exc: errors.APIError) -> str:
        text = str(exc.message or exc.status or "")
        if self._api_key:
            text = text.replace(self._api_key, "[REDACTED]")
        return redact(text)[:MAX_ERROR_CHARS]

    @staticmethod
    def _contents(parts: list[Part]) -> list[types.Part]:
        return [
            types.Part.from_bytes(data=part.data, mime_type=part.mime_type)
            if isinstance(part, BytesPart)
            else types.Part.from_text(text=part)
            for part in redact_parts(parts)
        ]

    @staticmethod
    def _usage(model: str, response: types.GenerateContentResponse) -> Usage:
        meta = response.usage_metadata
        if meta is None:
            return Usage(model=model, tokens_in=0, tokens_out=0)
        # Thinking tokens are billed as output.
        tokens_out = (meta.candidates_token_count or 0) + (meta.thoughts_token_count or 0)
        return Usage(model=model, tokens_in=meta.prompt_token_count or 0, tokens_out=tokens_out)

    async def _generate(
        self,
        model: str,
        parts: list[Part],
        *,
        system: str | None,
        timeout: float | None,
        tier: ModelTier,
        json_schema: dict[str, Any] | None = None,
    ) -> types.GenerateContentResponse:
        seconds = timeout or settings.LLM_TIMEOUT_SECONDS
        config = types.GenerateContentConfig(
            system_instruction=system,
            temperature=0,
            # FAST calls are short classifications; default thinking adds tens of seconds.
            thinking_config=FAST_THINKING if tier is ModelTier.FAST else None,
            safety_settings=SAFETY_SETTINGS,
            response_mime_type="application/json" if json_schema else None,
            response_json_schema=json_schema,
            http_options=types.HttpOptions(timeout=int(seconds * 1000)),
        )
        contents = self._contents(parts)
        attempts = settings.LLM_MAX_RETRIES + 1
        for attempt in range(1, attempts + 1):
            try:
                async with asyncio.timeout(seconds):
                    response = await self._client.aio.models.generate_content(
                        model=model, contents=contents, config=config
                    )
                break
            except errors.APIError as exc:
                if exc.code not in RETRYABLE_STATUS:
                    raise LLMRejected(
                        f"LLM provider rejected the request: {self._safe_message(exc)}",
                        details={"status": exc.code},
                    ) from None
                reason = f"status_{exc.code}"
            except TRANSIENT_ERRORS as exc:
                reason = type(exc).__name__
            if attempt == attempts:
                raise LLMUnavailable(
                    "LLM provider unavailable", details={"reason": reason, "attempts": attempts}
                )
            delay = min(BACKOFF_CAP_SECONDS, BACKOFF_BASE_SECONDS * 2 ** (attempt - 1))
            delay *= random.uniform(0.5, 1.0)
            logger.warning(
                "llm_retry",
                extra={"model": model, "attempt": attempt, "reason": reason, "delay_s": delay},
            )
            await self._sleep(delay)

        if not response.candidates:
            feedback = response.prompt_feedback
            reason = str(feedback.block_reason) if feedback and feedback.block_reason else None
            raise LLMRejected("LLM provider blocked the prompt", details={"reason": reason})
        return response

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
        model = model_for(tier)
        response = await self._generate(
            model,
            parts,
            system=system,
            timeout=timeout,
            tier=tier,
            json_schema=schema.model_json_schema(),
        )
        usage = self._usage(model, response)
        try:
            return schema.model_validate_json(response.text or ""), usage
        except ValidationError as exc:
            error = LLMInvalidOutput(
                "Model output did not match the schema", details={"schema": schema.__name__}
            )
            error.usage = usage  # type: ignore[attr-defined]
            raise error from exc

    async def generate_text(
        self,
        parts: list[Part],
        *,
        tier: ModelTier = ModelTier.FAST,
        system: str | None = None,
        timeout: float | None = None,
        meta: CallMeta | None = None,
    ) -> tuple[str, Usage]:
        model = model_for(tier)
        response = await self._generate(model, parts, system=system, timeout=timeout, tier=tier)
        return response.text or "", self._usage(model, response)

    async def transcribe(
        self,
        audio: bytes,
        mime_type: str,
        language: str | None = None,
        *,
        meta: CallMeta | None = None,
    ) -> tuple[str, Usage]:
        instruction = TRANSCRIBE_INSTRUCTION
        if language in TRANSCRIBE_LANGUAGES:
            instruction += f" The expected language is {TRANSCRIBE_LANGUAGES[language]}."
        return await self.generate_text(
            [BytesPart(audio, mime_type), instruction], tier=ModelTier.FAST, meta=meta
        )
