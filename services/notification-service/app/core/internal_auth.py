"""Service JWTs from core-api (HS256, shared INTERNAL_JWT_SECRET)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import jwt
from fastapi import Request

from app.core.config import settings
from app.core.errors import Forbidden, Unauthorized

ALGORITHM = "HS256"
MAX_TOKEN_LIFETIME_SECONDS = 300
LEEWAY_SECONDS = 5
EXPECTED_AUDIENCE = "notification-service"
EXPECTED_ISSUER = "core-api"


@dataclass(frozen=True)
class ServiceIdentity:
    service: str
    claims: dict[str, Any]


def _secret() -> str:
    return settings.INTERNAL_JWT_SECRET.get_secret_value()


def verify_core_token(token: str) -> dict[str, Any]:
    try:
        claims = jwt.decode(
            token,
            _secret(),
            algorithms=[ALGORITHM],
            audience=EXPECTED_AUDIENCE,
            issuer=EXPECTED_ISSUER,
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


def _bearer(request: Request) -> str:
    scheme, _, token = request.headers.get("Authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise Unauthorized("Missing service token", code="service_token_missing")
    return token.strip()


async def require_core(request: Request) -> ServiceIdentity:
    claims = verify_core_token(_bearer(request))
    return ServiceIdentity(service=str(claims.get("iss")), claims=claims)
