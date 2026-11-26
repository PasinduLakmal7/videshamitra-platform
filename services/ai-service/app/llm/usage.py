"""LLM usage ledger, cost estimates and the daily token budget (fails closed)."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Protocol

import asyncpg

from app.core.config import settings
from app.llm.base import (
    BudgetExceeded,
    CallMeta,
    LLMClient,
    LLMUnavailable,
    ModelTier,
    Part,
    T,
    Usage,
)

logger = logging.getLogger(__name__)

# USD per 1M tokens (input, output incl. thinking), Google list price 2026-11. Estimates only;
# the daily budget is enforced on tokens, not cost. Unknown models are costed at 0.
PRICE_PER_MTOK: dict[str, tuple[Decimal, Decimal]] = {
    "gemini-3.5-flash": (Decimal("1.50"), Decimal("9.00")),
}
UNSPECIFIED = CallMeta(purpose="unspecified")


def estimate_cost(usage: Usage) -> Decimal:
    price_in, price_out = PRICE_PER_MTOK.get(usage.model, (Decimal(0), Decimal(0)))
    cost = (usage.tokens_in * price_in + usage.tokens_out * price_out) / Decimal(1_000_000)
    return cost.quantize(Decimal("0.000001"))


class UsageStore(Protocol):
    async def tokens_used_today(self) -> int: ...

    async def record(self, usage: Usage, cost: Decimal, meta: CallMeta) -> None: ...


@dataclass
class InMemoryUsageStore:
    used: int = 0
    rows: list[tuple[Usage, Decimal, CallMeta]] = field(default_factory=list)

    async def tokens_used_today(self) -> int:
        return self.used

    async def record(self, usage: Usage, cost: Decimal, meta: CallMeta) -> None:
        self.used += usage.total
        self.rows.append((usage, cost, meta))


class PgUsageStore:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def tokens_used_today(self) -> int:
        async with self._pool.acquire() as conn:
            return await conn.fetchval(
                """
                select coalesce(sum(tokens_in + tokens_out), 0)::bigint from ai.llm_usage
                where created_at >= date_trunc('day', now() at time zone 'utc') at time zone 'utc'
                """
            )

    async def record(self, usage: Usage, cost: Decimal, meta: CallMeta) -> None:
        async with self._pool.acquire() as conn, conn.transaction():
            await conn.execute(
                """
                insert into ai.llm_usage (model, purpose, run_id, tokens_in, tokens_out, cost_usd)
                values ($1, $2, $3, $4, $5, $6)
                """,
                usage.model,
                meta.purpose,
                meta.run_id,
                usage.tokens_in,
                usage.tokens_out,
                cost,
            )
            if meta.run_id is not None:
                await conn.execute(
                    """
                    update ai.analysis_runs
                    set tokens_in = tokens_in + $2, tokens_out = tokens_out + $3,
                        cost_usd = cost_usd + $4, model = $5
                    where id = $1
                    """,
                    meta.run_id,
                    usage.tokens_in,
                    usage.tokens_out,
                    cost,
                    usage.model,
                )


class MeteredLLM:
    """Wraps a provider: budget check before every call, usage recorded after."""

    def __init__(self, inner: LLMClient, store: UsageStore, budget: int | None = None) -> None:
        self._inner = inner
        self._store = store
        self._budget = settings.LLM_DAILY_TOKEN_BUDGET if budget is None else budget

    async def _check_budget(self) -> None:
        try:
            used = await self._store.tokens_used_today()
        except Exception as exc:
            logger.error("llm_budget_check_failed", extra={"error": type(exc).__name__})
            raise LLMUnavailable("LLM usage store unavailable") from None
        if used >= self._budget:
            logger.warning("llm_budget_exceeded", extra={"used": used, "budget": self._budget})
            raise BudgetExceeded("Daily LLM token budget exhausted")

    async def _record(self, usage: Usage, meta: CallMeta | None) -> None:
        meta = meta or UNSPECIFIED
        try:
            await self._store.record(usage, estimate_cost(usage), meta)
        except Exception as exc:
            logger.error(
                "llm_usage_record_failed",
                extra={"error": type(exc).__name__, "purpose": meta.purpose},
            )

    async def _run(
        self, call: Callable[[], Awaitable[tuple[Any, Usage]]], meta: CallMeta | None
    ) -> tuple[Any, Usage]:
        await self._check_budget()
        try:
            result, usage = await call()
        except Exception as exc:
            spent = getattr(exc, "usage", None)
            if isinstance(spent, Usage):
                await self._record(spent, meta)
            raise
        await self._record(usage, meta)
        return result, usage

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
        return await self._run(
            lambda: self._inner.generate_json(
                parts, schema, tier=tier, system=system, timeout=timeout, meta=meta
            ),
            meta,
        )

    async def generate_text(
        self,
        parts: list[Part],
        *,
        tier: ModelTier = ModelTier.FAST,
        system: str | None = None,
        timeout: float | None = None,
        meta: CallMeta | None = None,
    ) -> tuple[str, Usage]:
        return await self._run(
            lambda: self._inner.generate_text(
                parts, tier=tier, system=system, timeout=timeout, meta=meta
            ),
            meta,
        )

    async def transcribe(
        self,
        audio: bytes,
        mime_type: str,
        language: str | None = None,
        *,
        meta: CallMeta | None = None,
    ) -> tuple[str, Usage]:
        return await self._run(
            lambda: self._inner.transcribe(audio, mime_type, language, meta=meta), meta
        )
