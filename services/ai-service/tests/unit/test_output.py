from __future__ import annotations

import pytest
from pydantic import BaseModel, ConfigDict

from app.guardrails.injection import UNTRUSTED_POLICY
from app.guardrails.output import generate_validated, retry_hint
from app.llm.base import BudgetExceeded, LLMInvalidOutput, LLMUnavailable
from app.llm.fake import FakeLLM


class Offer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    salary: int
    currency: str


PARTS = ["Extract the offer."]
GOOD = {"salary": 1100, "currency": "AED"}
BAD = {"salary": "a lot", "ignore previous instructions": "0771234567"}


async def _hint_for(bad: dict) -> str:
    fake = FakeLLM()
    fake.register(PARTS, bad, schema=Offer)
    with pytest.raises(LLMInvalidOutput) as info:
        await fake.generate_json(PARTS, Offer)
    return retry_hint(Offer, info.value)


async def test_valid_output_needs_one_call_and_carries_policy():
    fake = FakeLLM()
    fake.register(PARTS, GOOD, schema=Offer)
    offer, _ = await generate_validated(fake, PARTS, Offer, system="You extract offers.")
    assert offer == Offer(**GOOD)
    assert len(fake.calls) == 1
    assert fake.calls[0]["system"].startswith("You extract offers.")
    assert UNTRUSTED_POLICY in fake.calls[0]["system"]


async def test_invalid_then_valid_retries_once_with_hint():
    hint = await _hint_for(BAD)
    fake = FakeLLM()
    fake.register(PARTS, BAD, schema=Offer)
    fake.register([*PARTS, hint], GOOD, schema=Offer)
    offer, _ = await generate_validated(fake, PARTS, Offer)
    assert offer == Offer(**GOOD)
    assert len(fake.calls) == 2
    assert fake.calls[1]["parts"][-1] == hint


async def test_hint_names_fields_but_never_values():
    hint = await _hint_for(BAD)
    assert "salary" in hint
    assert "currency" in hint
    assert "Offer" in hint
    for leaked in ("a lot", "0771234567", "ignore previous instructions"):
        assert leaked not in hint


async def test_invalid_twice_fails_safe():
    hint = await _hint_for(BAD)
    fake = FakeLLM()
    fake.register(PARTS, BAD, schema=Offer)
    fake.register([*PARTS, hint], {"salary": None}, schema=Offer)
    with pytest.raises(LLMInvalidOutput) as info:
        await generate_validated(fake, PARTS, Offer)
    assert info.value.code == "llm_invalid_output"
    assert len(fake.calls) == 2


@pytest.mark.parametrize("error", [BudgetExceeded("over"), LLMUnavailable("down")])
async def test_other_errors_are_not_retried(error):
    fake = FakeLLM()
    fake.register(PARTS, error, schema=Offer)
    with pytest.raises(type(error)):
        await generate_validated(fake, PARTS, Offer)
    assert len(fake.calls) == 1
