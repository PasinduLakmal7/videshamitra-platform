"""Service JWTs between core-api and ai-service (HS256, shared INTERNAL_JWT_SECRET)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from fastapi import Request

from app.core.config import settings
from app.core.errors import Forbidden, Unauthorized

ALGORITHM = "HS256"
MAX_TOKEN_LIFETIME_SECONDS = 300
LEEWAY_SECONDS = 5
OUTBOUND_TTL_SECONDS = 60
SERVICE_NAME = "ai-service"
CORE_SERVICE = "core-api"


def _secret() -> str:
    return settings.INTERNAL_JWT_SECRET.get_secret_value()


def create_core_token() -> str:
    now = datetime.now(UTC)
    claims = {
        "iss": SERVICE_NAME,
        "aud": CORE_SERVICE,
        "sub": SERVICE_NAME,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=OUTBOUND_TTL_SECONDS)).timestamp()),
    }
    return jwt.encode(claims, _secret(), algorithm=ALGORITHM)


def verify_core_token(token: str) -> dict[str, Any]:
    try:
        claims = jwt.decode(
            token,
            _secret(),
            algorithms=[ALGORITHM],
            audience=SERVICE_NAME,
            issuer=CORE_SERVICE,
            leeway=LEEWAY_SECONDS,
            options={"require": ["iss", "aud", "sub", "exp", "iat"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise Unauthorized("Service token expired", code="service_token_expired") from exc
    except jwt.InvalidAudienceError as exc:
        raise Forbidden("Service token audience mismatch", code="service_token_audience") from exc
    except jwt.InvalidIssuerError as exc:
        raise Forbidden("Service token issuer not allowed", code="service_token_issuer") from exc
    except jwt.InvalidTokenError as exc:
        raise Unauthorized("Invalid service token", code="service_token_invalid") from exc

    if int(claims["exp"]) - int(claims["iat"]) > MAX_TOKEN_LIFETIME_SECONDS:
        raise Unauthorized("Service token lifetime too long", code="service_token_lifetime")
    return claims


async def require_core(request: Request) -> dict[str, Any]:
    scheme, _, token = request.headers.get("Authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise Unauthorized("Missing service token", code="service_token_missing")
    return verify_core_token(token.strip())
