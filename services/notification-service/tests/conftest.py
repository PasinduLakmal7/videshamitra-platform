"""Test bootstrap: set the environment before the app is imported."""

from __future__ import annotations

import os
import time

import jwt
import pytest

os.environ["ENVIRONMENT"] = "test"
os.environ["INTERNAL_JWT_SECRET"] = "test-internal-secret-at-least-32-chars"
os.environ["DATABASE_URL"] = "postgresql://postgres:postgres@localhost:5432/postgres"
os.environ["MIGRATION_DATABASE_URL"] = os.environ["DATABASE_URL"]
os.environ["REDIS_URL"] = "redis://localhost:6379/0"
os.environ["PUSH_PROVIDER"] = "stub"
os.environ["WHATSAPP_ENABLED"] = "false"

SECRET = os.environ["INTERNAL_JWT_SECRET"]


@pytest.fixture
def core_token():
    def make(
        *,
        iss: str = "core-api",
        aud: str = "notification-service",
        sub: str | None = "core-api",
        ttl: int = 60,
        iat_offset: int = 0,
        secret: str = SECRET,
        drop: tuple[str, ...] = (),
    ) -> str:
        now = int(time.time()) + iat_offset
        claims = {"iss": iss, "aud": aud, "sub": sub, "iat": now, "exp": now + ttl}
        for key in drop:
            claims.pop(key, None)
        return jwt.encode(claims, secret, algorithm="HS256")

    return make
