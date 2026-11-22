"""Short-lived service-to-service JWTs.

Public Supabase tokens are never accepted on internal routes: they carry the
`authenticated` audience and are signed by Supabase, not by us.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from fastapi import Request

from app.core.config import settings
from app.core.exceptions import Forbidden, Unauthorized
from app.models.entities import ServiceIdentity

ALGORITHM = "HS256"
MAX_TOKEN_LIFETIME_SECONDS = 300


def create_service_token(
    target_audience: str,
    *,
    subject: str = "core-api",
    ttl_seconds: int | None = None,
) -> str:
    ttl = min(ttl_seconds or settings.INTERNAL_JWT_TTL_SECONDS, MAX_TOKEN_LIFETIME_SECONDS)
    now = datetime.now(UTC)
    claims = {
        "iss": settings.INTERNAL_JWT_ISSUER,
        "aud": target_audience,
        "sub": subject,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=ttl)).timestamp()),
    }
    return jwt.encode(claims, settings.INTERNAL_JWT_SECRET, algorithm=ALGORITHM)


def verify_service_token(
    token: str,
    *,
    expected_audience: str | None = None,
    allowed_issuers: list[str] | None = None,
) -> dict[str, Any]:
    audience = expected_audience or settings.INTERNAL_JWT_AUDIENCE
    issuers = allowed_issuers or settings.INTERNAL_ALLOWED_ISSUERS
    try:
        claims = jwt.decode(
            token,
            settings.INTERNAL_JWT_SECRET,
            algorithms=[ALGORITHM],
            audience=audience,
            leeway=5,
            options={"require": ["iss", "aud", "sub", "exp", "iat"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise Unauthorized("Service token expired", code="service_token_expired") from exc
    except jwt.InvalidAudienceError as exc:
        raise Forbidden("Service token audience mismatch", code="service_token_audience") from exc
    except jwt.InvalidTokenError as exc:
        raise Unauthorized("Invalid service token", code="service_token_invalid") from exc

    if int(claims["exp"]) - int(claims["iat"]) > MAX_TOKEN_LIFETIME_SECONDS:
        raise Unauthorized("Service token lifetime too long", code="service_token_lifetime")
    if claims.get("iss") not in issuers:
        raise Forbidden("Service token issuer not allowed", code="service_token_issuer")
    return claims


def _bearer(request: Request) -> str:
    header = request.headers.get("Authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise Unauthorized("Missing service token", code="service_token_missing")
    return token.strip()


async def require_service(request: Request) -> ServiceIdentity:
    claims = verify_service_token(_bearer(request))
    return ServiceIdentity(service=str(claims.get("iss")), claims=claims)


def require_service_from(*issuers: str) -> Callable[[Request], Awaitable[ServiceIdentity]]:
    async def dependency(request: Request) -> ServiceIdentity:
        claims = verify_service_token(_bearer(request), allowed_issuers=list(issuers))
        return ServiceIdentity(service=str(claims.get("iss")), claims=claims)

    return dependency
