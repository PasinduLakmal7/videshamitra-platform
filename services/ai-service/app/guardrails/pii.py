"""PII redaction applied before every log line and every LLM call."""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Callable

# ASCII-only boundaries: Sinhala/Tamil letters glued to a number must not shield it.
_L = r"(?<![0-9A-Za-z-])"
_R = r"(?![0-9A-Za-z-])"

_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+")
_BANK = re.compile(
    r"(?i)(?:\b(?:account|acct|a/c|acc)\b|\bbank\b|ගිණුම|கணக்கு)"
    r"[^0-9\n]{0,25}"
    rf"(?P<value>\d(?:[ -]?\d){{7,17}}){_R}"
)
_NIC = re.compile(rf"{_L}(?:\d{{12}}|\d{{9}}[VvXx]){_R}")
_PASSPORT = re.compile(rf"{_L}[A-Z]{{1,2}}\d{{7}}{_R}")
_PHONE = re.compile(r"(?<![0-9A-Za-z+-])\+?\d[\d\s-]{6,18}\d" + _R)

_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("EMAIL", _EMAIL),
    ("BANK_ACCOUNT", _BANK),
    ("NIC", _NIC),
    ("PASSPORT", _PASSPORT),
    ("PHONE", _PHONE),
)


def _apply(text: str, label: Callable[[str, str], str]) -> str:
    for kind, pattern in _RULES:

        def sub(match: re.Match[str], kind: str = kind) -> str:
            if "value" in match.groupdict():
                start, end = match.span("value")
                offset = match.start()
                whole = match.group()
                tag = label(kind, match.group("value"))
                return whole[: start - offset] + tag + whole[end - offset :]
            value = match.group()
            if kind == "PHONE" and not 9 <= sum(ch.isdigit() for ch in value) <= 15:
                return value
            return label(kind, value)

        text = pattern.sub(sub, text)
    return text


def redact(text: str) -> str:
    return _apply(text, lambda kind, _value: f"[{kind}]")


def redact_with_mapping(text: str) -> tuple[str, dict[str, str]]:
    """Numbered placeholders ([PHONE_1]); the mapping lets user-facing output be restored."""
    counts: Counter[str] = Counter()
    tags: dict[str, str] = {}

    def label(kind: str, value: str) -> str:
        if value not in tags:
            counts[kind] += 1
            tags[value] = f"[{kind}_{counts[kind]}]"
        return tags[value]

    redacted = _apply(text, label)
    return redacted, {tag: value for value, tag in tags.items()}


def restore(text: str, mapping: dict[str, str]) -> str:
    for tag, value in mapping.items():
        text = text.replace(tag, value)
    return text
