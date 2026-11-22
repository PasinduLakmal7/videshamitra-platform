"""Text normalisation helpers (agency names, phones, search)."""

from __future__ import annotations

import re
import unicodedata

_WHITESPACE = re.compile(r"\s+")
_NON_WORD = re.compile(r"[^\w\s]")
_PHONE = re.compile(r"[^\d+]")


def normalize_name(value: str | None) -> str:
    if not value:
        return ""
    text = unicodedata.normalize("NFKC", value).casefold()
    text = text.replace("&", " and ")
    text = _NON_WORD.sub(" ", text)
    text = _WHITESPACE.sub(" ", text).strip()
    return text


def normalize_phone(value: str | None) -> str | None:
    if not value:
        return None
    phone = _PHONE.sub("", value)
    if phone.startswith("00"):
        phone = "+" + phone[2:]
    return phone or None


def normalize_license_no(value: str | None) -> str | None:
    if not value:
        return None
    return re.sub(r"\s+", "", value).upper()
