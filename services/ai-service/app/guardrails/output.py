"""Structured LLM output: Pydantic-validated, retried once with an error hint, then fail safe."""

from __future__ import annotations

import logging
import re

from pydantic import ValidationError

from app.guardrails.injection import with_policy
from app.llm.base import CallMeta, LLMClient, LLMInvalidOutput, ModelTier, Part, T, Usage

logger = logging.getLogger(__name__)

MAX_HINT_FIELDS = 10
_SAFE_LOC = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,40}")


def _loc(parts: tuple[int | str, ...]) -> str:
    # Keys can come from model output (extra fields), so unknown-looking ones are masked.
    shown = [str(p) if isinstance(p, int) or _SAFE_LOC.fullmatch(p) else "?" for p in parts]
    return ".".join(shown) or "(root)"


def retry_hint(schema: type[T], exc: LLMInvalidOutput) -> str:
    cause = exc.__cause__
    problems = []
    if isinstance(cause, ValidationError):
        problems = [f"{_loc(e['loc'])} ({e['type']})" for e in cause.errors()[:MAX_HINT_FIELDS]]
    return (
        f"Your previous answer did not match the required JSON schema {schema.__name__}. "
        f"Problems at: {', '.join(problems) or 'unknown'}. "
        "Return only JSON that matches the schema."
    )


async def generate_validated(
    llm: LLMClient,
    parts: list[Part],
    schema: type[T],
    *,
    tier: ModelTier = ModelTier.FAST,
    system: str | None = None,
    timeout: float | None = None,
    meta: CallMeta | None = None,
) -> tuple[T, Usage]:
    system_prompt = with_policy(system)
    try:
        return await llm.generate_json(
            parts, schema, tier=tier, system=system_prompt, timeout=timeout, meta=meta
        )
    except LLMInvalidOutput as exc:
        logger.warning("llm_output_invalid", extra={"schema": schema.__name__, "attempt": 1})
        hint = retry_hint(schema, exc)
    try:
        return await llm.generate_json(
            [*parts, hint], schema, tier=tier, system=system_prompt, timeout=timeout, meta=meta
        )
    except LLMInvalidOutput:
        logger.error("llm_output_invalid", extra={"schema": schema.__name__, "attempt": 2})
        raise LLMInvalidOutput(
            "Model output failed validation after one retry", details={"schema": schema.__name__}
        ) from None
