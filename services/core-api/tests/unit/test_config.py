"""Configuration fail-fast and URL splitting."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_settings_fail_fast_without_required_values(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("INTERNAL_JWT_SECRET", raising=False)
    with pytest.raises(ValidationError) as exc:
        Settings(_env_file=None)
    missing = {error["loc"][0] for error in exc.value.errors()}
    assert {"DATABASE_URL", "INTERNAL_JWT_SECRET"} <= missing


def test_supabase_internal_and_public_urls_split() -> None:
    settings = Settings(
        _env_file=None,
        DATABASE_URL="postgresql://localhost/test",
        INTERNAL_JWT_SECRET="test-internal-secret-at-least-32-chars",
        SUPABASE_URL="http://localhost:54321",
        SUPABASE_INTERNAL_URL="http://host.docker.internal:54321",
    )
    assert settings.supabase_jwks_url == (
        "http://host.docker.internal:54321/auth/v1/.well-known/jwks.json"
    )
    assert settings.storage_internal_base_url == ("http://host.docker.internal:54321/storage/v1")
    assert settings.storage_public_base_url == "http://localhost:54321/storage/v1"
