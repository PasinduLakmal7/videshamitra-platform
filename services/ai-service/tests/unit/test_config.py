from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.config import Settings

STRONG = "x" * 40


def make(**overrides) -> Settings:
    values = {
        "INTERNAL_JWT_SECRET": STRONG,
        "GEMINI_API_KEY": "gemini-key",
        "FINGERPRINT_PEPPER": STRONG,
        **overrides,
    }
    return Settings(_env_file=None, **values)


def test_environment_defaults_to_production(monkeypatch):
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    assert make().ENVIRONMENT == "production"


def test_short_internal_secret_rejected_everywhere():
    with pytest.raises(ValidationError):
        make(ENVIRONMENT="development", INTERNAL_JWT_SECRET="short")


@pytest.mark.parametrize(
    "overrides",
    [
        {"INTERNAL_JWT_SECRET": "replace-with-a-long-random-internal-secret"},
        {"GEMINI_API_KEY": ""},
        {"FINGERPRINT_PEPPER": ""},
        {"FINGERPRINT_PEPPER": "too-short"},
    ],
)
def test_production_rejects_weak_or_missing_secrets(overrides):
    with pytest.raises(ValidationError):
        make(ENVIRONMENT="production", **overrides)


def test_development_allows_missing_optional_secrets():
    settings = make(ENVIRONMENT="development", GEMINI_API_KEY="", FINGERPRINT_PEPPER="")
    assert settings.is_dev


def test_secrets_not_in_repr():
    settings = make(ENVIRONMENT="production", WHATSAPP_ACCESS_TOKEN="wa-token-value")
    text = repr(settings) + str(settings.model_dump())
    for secret in (STRONG, "gemini-key", "wa-token-value"):
        assert secret not in text
