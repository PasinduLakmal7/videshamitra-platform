from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import BaseModel

from app.llm.base import BudgetExceeded, CallMeta, LLMInvalidOutput, LLMUnavailable, Usage
from app.llm.fake import FakeLLM
from app.llm.usage import InMemoryUsageStore, MeteredLLM, estimate_cost


class Label(BaseModel):
    label: str


def test_estimate_cost():
    assert estimate_cost(Usage("gemini-3.5-flash", 1_000_000, 0)) == Decimal("1.500000")
    assert estimate_cost(Usage("gemini-3.5-flash", 1000, 1000)) == Decimal("0.010500")
    assert estimate_cost(Usage("unknown-model", 1000, 1000)) == Decimal("0")


async def test_usage_recorded_with_meta():
    fake = FakeLLM()
    fake.register(["x"], {"label": "a"}, schema=Label)
    store = InMemoryUsageStore()
    run_id = uuid4()
    llm = MeteredLLM(fake, store, budget=10_000)
    result, usage = await llm.generate_json(
        ["x"], Label, meta=CallMeta(purpose="classify", run_id=run_id)
    )
    assert result.label == "a"
    assert store.used == usage.total
    recorded_usage, cost, meta = store.rows[0]
    assert recorded_usage == usage
    assert meta == CallMeta(purpose="classify", run_id=run_id)
    assert cost == estimate_cost(usage)


async def test_budget_guard_blocks_when_exhausted():
    fake = FakeLLM()
    fake.register(["x"], "ok")
    store = InMemoryUsageStore(used=500)
    llm = MeteredLLM(fake, store, budget=500)
    with pytest.raises(BudgetExceeded) as caught:
        await llm.generate_text(["x"])
    assert caught.value.code == "budget_exceeded"
    assert fake.calls == []


async def test_budget_reached_after_calls():
    fake = FakeLLM()
    fake.register(["x"], "ok")
    store = InMemoryUsageStore()
    llm = MeteredLLM(fake, store, budget=1)
    await llm.generate_text(["x"])
    with pytest.raises(BudgetExceeded):
        await llm.generate_text(["x"])
    assert len(fake.calls) == 1


class BrokenStore(InMemoryUsageStore):
    async def tokens_used_today(self) -> int:
        raise ConnectionError("db down")


async def test_store_failure_fails_closed():
    fake = FakeLLM()
    fake.register(["x"], "ok")
    llm = MeteredLLM(fake, BrokenStore(), budget=10_000)
    with pytest.raises(LLMUnavailable):
        await llm.generate_text(["x"])
    assert fake.calls == []


async def test_failed_call_with_usage_is_still_recorded():
    error = LLMInvalidOutput("bad json")
    error.usage = Usage("gemini-2.5-flash", 40, 2)
    fake = FakeLLM()
    fake.register(["x"], error)
    store = InMemoryUsageStore()
    llm = MeteredLLM(fake, store, budget=10_000)
    with pytest.raises(LLMInvalidOutput):
        await llm.generate_text(["x"])
    assert store.used == 42
