"""User-facing safety: footer with hotline 1989, banned legality claims, no profiling questions."""

from __future__ import annotations

import re
from datetime import date

HOTLINE = "1989"

# si/ta wording pending native-speaker review (Person 3).
_FOOTER = {
    "en": "Independent AI assistant, not SLBFE. Official list date: {date}. SLBFE hotline: 1989.",
    "si": "මෙය ස්වාධීන AI සහායකයෙකි, SLBFE නොවේ. නිල ලැයිස්තු දිනය: {date}. SLBFE ඇමතුම් අංකය: 1989.",
    "ta": "இது ஒரு சுயாதீன AI உதவியாளர், SLBFE அல்ல. அதிகாரப்பூர்வ பட்டியல் தேதி: {date}. "
    "SLBFE உதவி எண்: 1989.",
}
_NO_DATE = {"en": "not available", "si": "නොමැත", "ta": "கிடைக்கவில்லை"}
_NEUTRAL = {
    "en": "Please check the official SLBFE list status shown above.",
    "si": "කරුණාකර ඉහත පෙන්වා ඇති නිල SLBFE ලැයිස්තු තත්ත්වය පරීක්ෂා කරන්න.",
    "ta": "மேலே காட்டப்பட்டுள்ள அதிகாரப்பூர்வ SLBFE பட்டியல் நிலையைச் சரிபார்க்கவும்.",
}

_SENTENCE = re.compile(r"[^.!?\n]+[.!?]*")

_EN_BANNED = re.compile(
    r"(?i)\b(?:agency|agencies|company|recruiter|employer|job|offer|it|this|they)\b[^.!?\n]{0,30}?"
    r"\b(?:is|are|looks|seems|appears)\s+(?:(?:100%|completely|totally|fully|definitely|very)\s+)?"
    r"(?:legal|safe|legit(?:imate)?|genuine|trustworthy|guaranteed|government[\s-]approved)\b"
    r"|\b100\s*%\s*(?:safe|legal|legit|genuine)\b"
)
_SI_AGENCY = re.compile(r"නියෝජිත|ආයතනය|සමාගම")
_SI_CLAIM = re.compile(r"නීත්‍?යානුකූල|ආරක්ෂිත|විශ්වාසදායක")
_SI_NEGATION = re.compile(r"නොවේ|නැත|නොහැක")
_TA_AGENCY = re.compile(r"முகவர்|நிறுவனம்")
_TA_CLAIM = re.compile(r"சட்டபூர்வ|பாதுகாப்பான|நம்பகமான")
_TA_NEGATION = re.compile(r"அல்ல|இல்லை")

_PROFILE_TOPIC = re.compile(
    r"(?i)\b(?:ethnicity|ethnic|race|religion|religious|caste|faith)\b"
    r"|කුලය|ආගම|ජාතිය|ජනවර්ග|சாதி|மதம்|இனம்"
)
_PROFILE_ASK = re.compile(r"(?i)\?|\byour\b|ඔබේ|ඔබගේ|உங்கள்|உன்")


def _locale(locale: str | None) -> str:
    return locale if locale in _FOOTER else "en"


def footer(locale: str | None, list_date: date | None) -> str:
    loc = _locale(locale)
    shown = list_date.isoformat() if list_date else _NO_DATE[loc]
    return _FOOTER[loc].format(date=shown)


def _is_banned(sentence: str) -> bool:
    if _EN_BANNED.search(sentence):
        return True
    for agency, claim, negation in (
        (_SI_AGENCY, _SI_CLAIM, _SI_NEGATION),
        (_TA_AGENCY, _TA_CLAIM, _TA_NEGATION),
    ):
        if agency.search(sentence) and claim.search(sentence) and not negation.search(sentence):
            return True
    return False


def _keep_leading_space(sentence: str, replacement: str) -> str:
    return sentence[: len(sentence) - len(sentence.lstrip())] + replacement


def scrub_banned_claims(text: str, locale: str | None = "en") -> tuple[str, list[str]]:
    """Replaces any sentence claiming an agency is legal or safe with a neutral pointer."""
    hits: list[str] = []
    neutral = _NEUTRAL[_locale(locale)]

    def sub(match: re.Match[str]) -> str:
        sentence = match.group()
        if not _is_banned(sentence):
            return sentence
        hits.append("banned_claim")
        return _keep_leading_space(sentence, neutral)

    return _SENTENCE.sub(sub, text), hits


def strip_profiling_questions(text: str) -> tuple[str, list[str]]:
    hits: list[str] = []

    def sub(match: re.Match[str]) -> str:
        sentence = match.group()
        if _PROFILE_TOPIC.search(sentence) and _PROFILE_ASK.search(sentence):
            hits.append("profiling_question")
            return ""
        return sentence

    cleaned = _SENTENCE.sub(sub, text)
    return re.sub(r"[ \t]{2,}", " ", cleaned).strip(), hits


def finalize_user_text(text: str, locale: str | None, list_date: date | None) -> str:
    """Every user-facing verdict or answer goes through this before it is sent."""
    text, _ = scrub_banned_claims(text, locale)
    text, _ = strip_profiling_questions(text)
    note = footer(locale, list_date)
    if note in text:
        return text
    return f"{text}\n\n{note}" if text else note
