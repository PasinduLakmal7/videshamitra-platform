"""Supabase access-token verification (JWKS with HS256 fallback)."""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx
import jwt
from jwt.algorithms import RSAAlgorithm

from app.core.config import settings
from app.core.exceptions import Unauthorized

logger = logging.getLogger(__name__)

_JWKS_TTL_SECONDS = 300


class SupabaseTokenVerifier:
    def __init__(self) -> None:
        self._jwks: list[dict[str, Any]] = []
        self._jwks_fetched_at = 0.0

    async def _get_jwks(self) -> list[dict[str, Any]]:
        now = time.monotonic()
        if self._jwks and now - self._jwks_fetched_at < _JWKS_TTL_SECONDS:
            return self._jwks
        url = settings.supabase_jwks_url
        if not url:
            return []
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(url)
                response.raise_for_status()
                self._jwks = response.json().get("keys", [])
                self._jwks_fetched_at = now
        except Exception as exc:
            logger.exception("jwks_fetch_failed")
            # Keep a previously cached key set if the fetch failed.
            if not self._jwks:
                raise Unauthorized("Unable to fetch signing keys", code="auth_unavailable") from exc
        return self._jwks

    async def _key_for(self, token: str) -> Any:
        header = jwt.get_unverified_header(token)
        alg = header.get("alg", "")
        if alg == "HS256":
            if not settings.SUPABASE_JWT_SECRET:
                raise Unauthorized(
                    "HS256 verification is not configured", code="auth_not_configured"
                )
            return settings.SUPABASE_JWT_SECRET

        kid = header.get("kid")
        keys = await self._get_jwks()
        for key in keys:
            if key.get("kid") == kid and key.get("alg", alg) == alg:
                if alg.startswith("RS"):
                    return RSAAlgorithm.from_jwk(key)
                if alg.startswith("ES"):
                    from jwt.algorithms import ECAlgorithm

                    return ECAlgorithm.from_jwk(key)
        raise Unauthorized("Unknown signing key", code="invalid_token")

    async def verify(self, token: str) -> dict[str, Any]:
        try:
            key = await self._key_for(token)
            options = {"require": ["sub", "exp"]}
            if not settings.jwt_issuer:
                options["verify_iss"] = False
            claims = jwt.decode(
                token,
                key,
                algorithms=["HS256", "RS256", "ES256"],
                audience=settings.JWT_AUDIENCE or None,
                issuer=settings.jwt_issuer or None,
                leeway=30,
                options=options,
            )
        except jwt.ExpiredSignatureError as exc:
            raise Unauthorized("Token expired", code="token_expired") from exc
        except jwt.InvalidAudienceError as exc:
            raise Unauthorized("Token audience mismatch", code="invalid_token") from exc
        except jwt.InvalidTokenError as exc:
            raise Unauthorized("Invalid token", code="invalid_token") from exc
        if not claims.get("sub"):
            raise Unauthorized("Token has no subject", code="invalid_token")
        return claims


_verifier = SupabaseTokenVerifier()


async def verify_supabase_token(token: str) -> dict[str, Any]:
    return await _verifier.verify(token)


def create_dev_token(user_id: str, *, ttl_seconds: int = 3600) -> str:
    """Development-only HS256 token accepted by the local Supabase secret.

    Refused in production by the caller. Useful for local demos without an SMS
    provider when `AUTH_DEV_OTP` is configured.
    """
    if settings.is_production:
        raise Unauthorized("Dev tokens are disabled", code="auth_not_configured")
    if not settings.SUPABASE_JWT_SECRET:
        raise Unauthorized("Dev token secret is not configured", code="auth_not_configured")
    now = int(time.time())
    claims = {
        "sub": user_id,
        "role": "authenticated",
        "aud": settings.JWT_AUDIENCE or "authenticated",
        "iss": settings.jwt_issuer or "videshamitra-dev",
        "iat": now,
        "exp": now + ttl_seconds,
    }
    return jwt.encode(claims, settings.SUPABASE_JWT_SECRET, algorithm="HS256")
