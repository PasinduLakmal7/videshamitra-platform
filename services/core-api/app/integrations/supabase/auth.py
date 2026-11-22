"""Thin Supabase Auth client (signup, password, phone OTP, refresh, logout)."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.core.config import settings
from app.core.exceptions import (
    Conflict,
    RateLimited,
    ServiceUnavailable,
    Unauthorized,
    UpstreamError,
)

logger = logging.getLogger(__name__)


class SupabaseAuthClient:
    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client or httpx.AsyncClient(timeout=settings.SUPABASE_TIMEOUT_SECONDS)

    async def aclose(self) -> None:
        await self._client.aclose()

    @property
    def configured(self) -> bool:
        return settings.supabase_configured

    def _require_config(self) -> None:
        if not self.configured:
            raise ServiceUnavailable("Supabase Auth is not configured", code="auth_not_configured")

    def _anon_headers(self) -> dict[str, str]:
        return {
            "apikey": settings.SUPABASE_ANON_KEY,
            "Authorization": f"Bearer {settings.SUPABASE_ANON_KEY}",
            "Content-Type": "application/json",
        }

    def _admin_headers(self) -> dict[str, str]:
        if not settings.supabase_admin_configured:
            raise ServiceUnavailable(
                "Supabase admin credentials are not configured",
                code="auth_admin_not_configured",
            )
        return {
            "apikey": settings.SUPABASE_SERVICE_ROLE_KEY,
            "Authorization": f"Bearer {settings.SUPABASE_SERVICE_ROLE_KEY}",
            "Content-Type": "application/json",
        }

    def _url(self, path: str) -> str:
        return f"{settings.supabase_api_url}{path}"

    def _handle_error(self, response: httpx.Response) -> None:
        try:
            body = response.json()
        except Exception:
            body = {}
        message = (
            body.get("msg")
            or body.get("error_description")
            or body.get("message")
            or body.get("error")
            or "Supabase Auth request failed"
        )
        status = response.status_code
        if status == 429:
            raise RateLimited("Too many authentication attempts; try again later")
        if status in (400, 401, 403, 422):
            if "already" in str(message).lower() or "exists" in str(message).lower():
                raise Conflict(str(message), code="user_exists")
            raise Unauthorized(str(message), code="auth_failed")
        raise UpstreamError("Supabase Auth is unavailable", service="supabase-auth")

    async def _post(
        self, path: str, *, json: dict[str, Any], headers: dict[str, str]
    ) -> dict[str, Any]:
        self._require_config()
        try:
            response = await self._client.post(self._url(path), json=json, headers=headers)
        except httpx.HTTPError as exc:
            raise UpstreamError("Supabase Auth is unreachable", service="supabase-auth") from exc
        if response.status_code >= 400:
            self._handle_error(response)
        return response.json() if response.content else {}

    async def sign_up(self, *, email: str, password: str, data: dict[str, Any]) -> dict[str, Any]:
        return await self._post(
            "/auth/v1/signup",
            json={"email": email, "password": password, "data": data},
            headers=self._anon_headers(),
        )

    async def password_login(self, *, email: str, password: str) -> dict[str, Any]:
        return await self._post(
            "/auth/v1/token?grant_type=password",
            json={"email": email, "password": password},
            headers=self._anon_headers(),
        )

    async def request_otp(
        self, *, phone: str, data: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"phone": phone, "create_user": True}
        if data:
            payload["data"] = data
        return await self._post("/auth/v1/otp", json=payload, headers=self._anon_headers())

    async def verify_otp(self, *, phone: str, token: str) -> dict[str, Any]:
        return await self._post(
            "/auth/v1/verify",
            json={"phone": phone, "token": token, "type": "sms"},
            headers=self._anon_headers(),
        )

    async def refresh(self, *, refresh_token: str) -> dict[str, Any]:
        return await self._post(
            "/auth/v1/token?grant_type=refresh_token",
            json={"refresh_token": refresh_token},
            headers=self._anon_headers(),
        )

    async def logout(self, access_token: str) -> None:
        self._require_config()
        headers = {
            "apikey": settings.SUPABASE_ANON_KEY,
            "Authorization": f"Bearer {access_token}",
        }
        try:
            response = await self._client.post(self._url("/auth/v1/logout"), headers=headers)
        except httpx.HTTPError as exc:
            raise UpstreamError("Supabase Auth is unreachable", service="supabase-auth") from exc
        if response.status_code >= 500:
            raise UpstreamError("Supabase Auth is unavailable", service="supabase-auth")

    async def admin_create_user(
        self,
        *,
        email: str | None = None,
        phone: str | None = None,
        password: str | None = None,
        email_confirm: bool = True,
        phone_confirm: bool = False,
        user_metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self._require_config()
        if not settings.supabase_admin_configured:
            raise ServiceUnavailable(
                "Supabase admin credentials are not configured",
                code="auth_admin_not_configured",
            )
        payload: dict[str, Any] = {
            "email_confirm": email_confirm,
            "phone_confirm": phone_confirm,
        }
        if email:
            payload["email"] = email
        if phone:
            payload["phone"] = phone
        if password:
            payload["password"] = password
        if user_metadata:
            payload["user_metadata"] = user_metadata
        try:
            response = await self._client.post(
                self._url("/auth/v1/admin/users"),
                json=payload,
                headers=self._admin_headers(),
            )
        except httpx.HTTPError as exc:
            raise UpstreamError("Supabase Auth is unreachable", service="supabase-auth") from exc
        if response.status_code == 422:
            # Usually "user already registered"; callers can look up by email.
            raise Conflict("Auth user already exists", code="user_exists")
        if response.status_code >= 400:
            self._handle_error(response)
        return response.json()

    async def health(self) -> bool:
        if not settings.supabase_api_url:
            return False
        try:
            response = await self._client.get(self._url("/auth/v1/health"), timeout=3.0)
            return response.status_code < 500
        except Exception:
            return False

    async def admin_list_users(self, *, per_page: int = 1000) -> list[dict[str, Any]]:
        """List auth users (used by the idempotent demo seeder and admin tools)."""
        self._require_config()
        if not settings.supabase_admin_configured:
            raise ServiceUnavailable(
                "Supabase admin credentials are not configured",
                code="auth_admin_not_configured",
            )
        try:
            response = await self._client.get(
                self._url("/auth/v1/admin/users"),
                params={"page": 1, "per_page": per_page},
                headers=self._admin_headers(),
            )
        except httpx.HTTPError as exc:
            raise UpstreamError("Supabase Auth is unreachable", service="supabase-auth") from exc
        if response.status_code >= 400:
            self._handle_error(response)
        return response.json().get("users", [])
