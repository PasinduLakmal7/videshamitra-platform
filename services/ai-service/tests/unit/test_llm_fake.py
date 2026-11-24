from __future__ import annotations

import pytest
from pydantic import BaseModel

from app.llm.base import BytesPart, CallMeta, LLMInvalidOutput, LLMUnavailable, ModelTier
from app.llm.fake import FakeLLM


class Label(BaseModel):
    label: str


async def test_registered_prompt_returns_typed_value():
    fake = FakeLLM()
    fake.register(["classify this"], {"label": "fee"}, schema=Label)
    first, usage = await fake.generate_json(["classify this"], Label)
    second, _ = await fake.generate_json(["classify this"], Label)
    assert first == second == Label(label="fee")
    assert usage.model


async def test_key_uses_redacted_text_and_calls_are_redacted():
    fake = FakeLLM()
    fake.register(["call 0771234567"], "ok")
    text, _ = await fake.generate_text(["call 0779999999"], meta=CallMeta(purpose="test"))
    assert text == "ok"
    assert fake.calls[0]["parts"] == ["call [PHONE]"]
    assert fake.calls[0]["meta"].purpose == "test"


async def test_tier_and_schema_are_part_of_the_key():
    fake = FakeLLM()
    fake.register(["x"], {"label": "a"}, schema=Label, tier=ModelTier.PRO)
    with pytest.raises(LLMInvalidOutput):
        await fake.generate_json(["x"], Label)
    with pytest.raises(LLMInvalidOutput):
        await fake.generate_text(["x"], tier=ModelTier.PRO)


async def test_registered_exception_is_raised():
    fake = FakeLLM()
    fake.register(["x"], LLMUnavailable("down"))
    with pytest.raises(LLMUnavailable):
        await fake.generate_text(["x"])


async def test_invalid_value_fails_schema():
    fake = FakeLLM()
    fake.register(["x"], {"nope": 1}, schema=Label)
    with pytest.raises(LLMInvalidOutput):
        await fake.generate_json(["x"], Label)


async def test_transcribe_keyed_on_audio():
    fake = FakeLLM()
    fake.register([BytesPart(b"audio", "audio/ogg")], "hello")
    text, _ = await fake.transcribe(b"audio", "audio/ogg")
    assert text == "hello"
