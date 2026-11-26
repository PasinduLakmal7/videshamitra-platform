from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.config import Settings

STRONG = "x" * 40


def make(**overrides) -> Settings:
    values = {
        "DATABASE_URL": "postgresql://notification_service_role:test@localhost/test",
        "INTERNAL_JWT_SECRET": STRONG,
        **overrides,
    }
    return Settings(_env_file=None, **values)


def test_environment_defaults_to_production(monkeypatch):
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    with pytest.raises(ValidationError):
        make(PUSH_PROVIDER="stub")
    assert make(ENVIRONMENT="development").ENVIRONMENT == "development"


def test_short_internal_secret_rejected_everywhere():
    with pytest.raises(ValidationError):
        make(ENVIRONMENT="development", INTERNAL_JWT_SECRET="short")


def test_stub_provider_rejected_outside_dev():
    with pytest.raises(ValidationError):
        make(ENVIRONMENT="production", PUSH_PROVIDER="stub")


def test_fcm_requires_project_and_credentials():
    with pytest.raises(ValidationError):
        make(ENVIRONMENT="development", PUSH_PROVIDER="fcm")
    with pytest.raises(ValidationError):
        make(ENVIRONMENT="development", PUSH_PROVIDER="fcm", FCM_PROJECT_ID="project")
    configured = make(
        ENVIRONMENT="development",
        PUSH_PROVIDER="fcm",
        FCM_PROJECT_ID="project",
        FCM_SERVICE_ACCOUNT_FILE="/tmp/fcm.json",
    )
    assert configured.PUSH_PROVIDER == "fcm"


def test_invalid_timezone_rejected():
    with pytest.raises(ValidationError):
        make(QUIET_HOURS_TIMEZONE="Not/AZone")


def test_whatsapp_requires_credentials_when_enabled():
    with pytest.raises(ValidationError):
        make(ENVIRONMENT="development", WHATSAPP_ENABLED=True)
    configured = make(
        ENVIRONMENT="development",
        WHATSAPP_ENABLED=True,
        WHATSAPP_PHONE_NUMBER_ID="phone",
        WHATSAPP_ACCESS_TOKEN="token",
    )
    assert configured.WHATSAPP_ENABLED
