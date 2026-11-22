"""JWT verification: public Supabase tokens vs internal service tokens."""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.core.config import settings
from app.core.exceptions import Forbidden, Unauthorized
from app.core.internal_auth import create_service_token, verify_service_token
from app.core.security import create_dev_token, verify_supabase_token


def _supabase_token(**overrides: object) -> str:
    now = int(time.time())
    claims = {
        "sub": "3c4b3c4b-3c4b-3c4b-3c4b-3c4b3c4b3c4b",
        "aud": settings.JWT_AUDIENCE,
        "iss": settings.jwt_issuer,
        "role": "authenticated",
        "iat": now,
        "exp": now + 3600,
    }
    claims.update(overrides)
    return jwt.encode(claims, settings.SUPABASE_JWT_SECRET, algorithm="HS256")


async def test_supabase_token_verifies() -> None:
    claims = await verify_supabase_token(_supabase_token())
    assert claims["role"] == "authenticated"


async def test_expired_supabase_token_rejected() -> None:
    token = _supabase_token(exp=int(time.time()) - 60)
    with pytest.raises(Unauthorized) as exc:
        await verify_supabase_token(token)
    assert exc.value.code == "token_expired"


async def test_wrong_audience_rejected() -> None:
    token = _supabase_token(aud="something-else")
    with pytest.raises(Unauthorized):
        await verify_supabase_token(token)


async def test_internal_token_audience_matrix() -> None:
    token = create_service_token("ai-service")
    claims = verify_service_token(
        token, expected_audience="ai-service", allowed_issuers=["core-api"]
    )
    assert claims["iss"] == "core-api"
    assert claims["sub"] == "core-api"
    with pytest.raises(Forbidden):
        verify_service_token(token, expected_audience="core-api", allowed_issuers=["core-api"])


async def test_internal_token_rejects_public_token() -> None:
    with pytest.raises((Forbidden, Unauthorized)):
        verify_service_token(_supabase_token(), expected_audience="core-api")


async def test_internal_token_requires_short_expiry() -> None:
    token = create_service_token("ai-service", ttl_seconds=9999)
    claims = verify_service_token(
        token, expected_audience="ai-service", allowed_issuers=["core-api"]
    )
    now = datetime.now(UTC).timestamp()
    assert claims["exp"] - now <= 300


def test_dev_token_refused_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    with pytest.raises(Unauthorized):
        create_dev_token("3c4b3c4b-3c4b-3c4b-3c4b-3c4b3c4b3c4b")


def test_internal_token_expiry() -> None:
    now = datetime.now(UTC)
    expired = jwt.encode(
        {
            "iss": "ai-service",
            "aud": "core-api",
            "sub": "ai-service",
            "iat": int((now - timedelta(minutes=6)).timestamp()),
            "exp": int((now - timedelta(minutes=5)).timestamp()),
        },
        settings.INTERNAL_JWT_SECRET,
        algorithm="HS256",
    )
    with pytest.raises(Unauthorized) as exc:
        verify_service_token(expired)
    assert exc.value.code == "service_token_expired"
