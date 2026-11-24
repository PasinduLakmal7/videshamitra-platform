"""Client for core-api internal endpoints, authenticated with a fresh service token per call."""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

import httpx

from app.core.config import settings
from app.core.errors import NotFound, UpstreamError
from app.core.internal_auth import create_core_token
from app.core.request_id import current_request_id, current_trace_id

logger = logging.getLogger(__name__)

TIMEOUT = httpx.Timeout(15.0, connect=3.0)
GET_ATTEMPTS = 3


class CoreApiClient:
    def __init__(self, base_url: str | None = None, *, client: httpx.AsyncClient | None = None):
        self._client = client or httpx.AsyncClient(
            base_url=(base_url or settings.CORE_API_URL).rstrip("/"), timeout=TIMEOUT
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {create_core_token()}",
            "X-Request-ID": current_request_id(),
            "X-Trace-ID": current_trace_id(),
        }

    async def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        attempts = GET_ATTEMPTS if method == "GET" else 1
        for attempt in range(1, attempts + 1):
            try:
                response = await self._client.request(
                    method, path, headers=self._headers(), **kwargs
                )
                break
            except httpx.TransportError as exc:
                logger.warning(
                    "core_api_transport_error",
                    extra={"path": path, "attempt": attempt, "error": type(exc).__name__},
                )
                if attempt == attempts:
                    raise UpstreamError("core-api is unreachable") from exc
        if response.status_code == 404:
            raise NotFound("core-api resource not found")
        if not response.is_success:
            raise UpstreamError(
                "core-api rejected the request", details={"status": response.status_code}
            )
        return response

    async def _get_data(self, path: str) -> dict[str, Any]:
        return (await self._request("GET", path)).json()["data"]

    async def get_document_bytes(self, document_id: UUID) -> tuple[bytes, str]:
        response = await self._request("GET", f"/internal/v1/documents/{document_id}/content")
        return response.content, response.headers.get("content-type", "application/octet-stream")

    async def get_verification(self, verification_id: UUID) -> dict[str, Any]:
        return await self._get_data(f"/internal/v1/verifications/{verification_id}")

    async def get_license_history(self, agency_id: UUID) -> dict[str, Any]:
        return await self._get_data(f"/internal/v1/agencies/{agency_id}/license-history")

    async def post_audit_event(
        self,
        action: str,
        *,
        entity_type: str | None = None,
        entity_id: UUID | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        await self._request(
            "POST",
            "/internal/v1/audit-events",
            json={
                "action": action,
                "entity_type": entity_type,
                "entity_id": str(entity_id) if entity_id else None,
                "metadata": metadata or {},
            },
        )
