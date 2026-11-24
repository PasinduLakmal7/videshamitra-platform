"""PII redaction applied before logs and LLM calls (minimal set; Phase 4 extends it)."""

from __future__ import annotations

import re

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
# Sri Lankan NIC: 12 digits (2016+) or 9 digits + V/X.
_NIC = re.compile(r"(?<![\w-])(?:\d{12}|\d{9}[VvXx])(?![\w-])")
# Hyphen/word boundaries keep UUIDs and ISO dates intact.
_PHONE = re.compile(r"(?<![\w+-])\+?\d[\d\s-]{6,18}\d(?![\w-])")


def _phone(match: re.Match[str]) -> str:
    digits = sum(ch.isdigit() for ch in match.group())
    return "[PHONE]" if 9 <= digits <= 15 else match.group()


def redact(text: str) -> str:
    text = _EMAIL.sub("[EMAIL]", text)
    text = _NIC.sub("[NIC]", text)
    return _PHONE.sub(_phone, text)
