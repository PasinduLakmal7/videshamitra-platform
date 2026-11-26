"""FCM HTTP v1 provider using a service-account OAuth2 token."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import httpx

from app.providers.base import DeliveryResult, PushMessage

logger = logging.getLogger(__name__)

_SCOPE = "https://www.googleapis.com/auth/firebase.messaging"
_INVALID_TOKEN_STATUSES = frozenset({"UNREGISTERED", "SENDER_ID_MISMATCH"})
_RETRYABLE_STATUSES = frozenset({"QUOTA_EXCEEDED", "UNAVAILABLE", "INTERNAL", "RESOURCE_EXHAUSTED"})
_AUTH_STATUSES = frozenset({"PERMISSION_DENIED", "THIRD_PARTY_AUTH_ERROR", "UNAUTHENTICATED"})


class FcmPushProvider:
    name = "fcm"

    def __init__(
        self,
        *,
        project_id: str,
        service_account_file: str = "",
        service_account_json: str = "",
        api_url: str = "https://fcm.googleapis.com",
        timeout: float = 15.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.project_id = project_id
        self.api_url = api_url.rstrip("/")
        self._client = client or httpx.AsyncClient(timeout=timeout)
        self._credentials = self._load_credentials(service_account_file, service_account_json)

    @staticmethod
    def _load_credentials(service_account_file: str, service_account_json: str):
        from google.oauth2 import service_account

        if service_account_json:
            return service_account.Credentials.from_service_account_info(
                json.loads(service_account_json), scopes=[_SCOPE]
            )
        if service_account_file:
            return service_account.Credentials.from_service_account_file(
                service_account_file, scopes=[_SCOPE]
            )
        return None

    async def _access_token(self) -> str:
        if self._credentials is None:
            raise RuntimeError("FCM service account credentials are not configured")
        if self._credentials.valid and self._credentials.token:
            return self._credentials.token
        from google.auth.transport.requests import Request

        def refresh() -> str:
            if not self._credentials.valid:
                self._credentials.refresh(Request())
            if not self._credentials.token:
                raise RuntimeError("FCM credential refresh returned no token")
            return self._credentials.token

        return await asyncio.to_thread(refresh)

    async def send(self, message: PushMessage) -> DeliveryResult:
        try:
            token = await self._access_token()
        except Exception as exc:
            logger.exception("fcm_token_refresh_failed")
            return DeliveryResult(
                success=False,
                error_code="provider_auth_error",
                error_message=type(exc).__name__,
            )

        payload = {
            "message": {
                "token": message.token,
                "notification": {"title": message.title, "body": message.body},
                "data": message.data,
            }
        }
        try:
            response = await self._client.post(
                f"{self.api_url}/v1/projects/{self.project_id}/messages:send",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
        except httpx.HTTPError as exc:
            logger.warning("fcm_transport_error", extra={"error": type(exc).__name__})
            return DeliveryResult(
                success=False,
                error_code="provider_unavailable",
                error_message=type(exc).__name__,
                retryable=True,
            )

        if response.is_success:
            body = self._json(response)
            return DeliveryResult(
                success=True,
                provider_message_id=body.get("name"),
                http_status=response.status_code,
            )
        return self._error_result(response)

    @staticmethod
    def _json(response: httpx.Response) -> dict[str, Any]:
        try:
            return response.json()
        except Exception:
            return {}

    def _error_result(self, response: httpx.Response) -> DeliveryResult:
        body = self._json(response)
        error = body.get("error") or {}
        status = str(error.get("status") or "")
        message = str(error.get("message") or response.text[:500])
        lowered = message.lower()
        retry_after = _retry_after(response)

        if status in _INVALID_TOKEN_STATUSES or (
            status == "INVALID_ARGUMENT" and "token" in lowered
        ):
            return DeliveryResult(
                success=False,
                error_code="device_unregistered" if status == "UNREGISTERED" else "invalid_token",
                error_message=message,
                invalid_token=True,
                http_status=response.status_code,
            )
        if status in _AUTH_STATUSES or response.status_code in (401, 403):
            return DeliveryResult(
                success=False,
                error_code="provider_auth_error",
                error_message=message,
                http_status=response.status_code,
            )
        if (
            status in _RETRYABLE_STATUSES
            or response.status_code == 429
            or response.status_code >= 500
        ):
            return DeliveryResult(
                success=False,
                error_code=status or "provider_retryable",
                error_message=message,
                retryable=True,
                retry_after_seconds=retry_after,
                http_status=response.status_code,
            )
        return DeliveryResult(
            success=False,
            error_code=status or "provider_rejected",
            error_message=message,
            http_status=response.status_code,
        )

    async def aclose(self) -> None:
        await self._client.aclose()


def _retry_after(response: httpx.Response) -> int | None:
    value = response.headers.get("Retry-After")
    if not value:
        return None
    try:
        return max(0, int(value))
    except ValueError:
        return None
