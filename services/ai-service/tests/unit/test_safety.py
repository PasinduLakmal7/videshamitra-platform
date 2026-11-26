from __future__ import annotations

from datetime import date

import pytest

from app.guardrails.safety import (
    HOTLINE,
    finalize_user_text,
    footer,
    scrub_banned_claims,
    strip_profiling_questions,
)

LIST_DATE = date(2026, 11, 1)
DISCLAIMER = {"en": "not SLBFE", "si": "SLBFE නොවේ", "ta": "SLBFE அல்ல"}


@pytest.mark.parametrize("locale", ["en", "si", "ta"])
def test_footer_has_disclaimer_hotline_and_list_date(locale):
    note = footer(locale, LIST_DATE)
    assert HOTLINE in note
    assert DISCLAIMER[locale] in note
    assert "2026-11-01" in note


def test_footer_without_date_and_unknown_locale():
    assert "not available" in footer("en", None)
    assert footer("fr", LIST_DATE) == footer("en", LIST_DATE)


@pytest.mark.parametrize(
    ("text", "locale"),
    [
        ("Good news. This agency is legal.", "en"),
        ("The company is 100% safe to work with.", "en"),
        ("It looks completely legit!", "en"),
        ("They are government-approved.", "en"),
        ("මෙම නියෝජිත ආයතනය නීත්‍යානුකූලයි.", "si"),
        ("මෙම ආයතනය ආරක්ෂිතයි.", "si"),
        ("இந்த முகவர் நிறுவனம் சட்டபூர்வமானது.", "ta"),
        ("இந்த முகவர் பாதுகாப்பானவர்.", "ta"),
    ],
)
def test_banned_legality_claims_are_replaced(text, locale):
    out, hits = scrub_banned_claims(text, locale)
    assert hits == ["banned_claim"]
    for word in ("legal", "safe", "legit", "approved", "නීත්‍යානුකූල", "ආරක්ෂිත", "சட்டபூர்வ"):
        assert word not in out
    assert "SLBFE" in out


@pytest.mark.parametrize(
    "text",
    [
        "Safe migration tips: always keep a copy of your contract.",
        "This agency is not legal to recruit for Kuwait.",
        "The agency was found in the official list as of 2026-11-01.",
        "මෙම නියෝජිත ආයතනය ආරක්ෂිත නොවේ.",
        "இந்த முகவர் பாதுகாப்பானவர் அல்ல.",
    ],
)
def test_ordinary_or_negative_statements_are_kept(text):
    assert scrub_banned_claims(text) == (text, [])


@pytest.mark.parametrize(
    "text",
    [
        "What is your religion?",
        "Please tell me your caste.",
        "Which ethnicity are you?",
        "ඔබේ ආගම කුමක්ද?",
        "உங்கள் சாதி என்ன?",
    ],
)
def test_profiling_questions_are_dropped(text):
    out, hits = strip_profiling_questions(f"Thanks. {text} Your offer has 2 findings.")
    assert hits == ["profiling_question"]
    assert out == "Thanks. Your offer has 2 findings."


def test_religious_holidays_in_a_contract_are_not_profiling():
    text = "The contract gives leave on religious holidays."
    assert strip_profiling_questions(text) == (text, [])


@pytest.mark.parametrize("locale", ["en", "si", "ta"])
def test_finalize_applies_everything_and_is_idempotent(locale):
    raw = "This agency is safe. What is your religion? Fee is above the cap."
    once = finalize_user_text(raw, locale, LIST_DATE)
    assert once.endswith(footer(locale, LIST_DATE))
    assert "is safe" not in once
    assert "religion" not in once
    assert "Fee is above the cap." in once
    assert finalize_user_text(once, locale, LIST_DATE) == once


def test_finalize_on_empty_text_returns_footer():
    assert finalize_user_text("", "en", None) == footer("en", None)
