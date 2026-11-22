"""Shared HTTP client for internal services with service-JWT auth."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.core.config import settings
from app.core.exceptions import AppError, NotFound, RateLimited, UpstreamError
from app.core.internal_auth import create_service_token
from app.core.request_id import current_request_id, current_trace_id

logger = logging.getLogger(__name__)


class BaseServiceClient:
    service_name = "upstream"

    def __init__(
        self,
        base_url: str,
        *,
        service_name: str,
        audience: str,
        timeout: float | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.service_name = service_name
        self.audience = audience
        self._client = client or httpx.AsyncClient(
            base_url=self.base_url,
            timeout=timeout or settings.INTERNAL_HTTP_TIMEOUT_SECONDS,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    def headers(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {create_service_token(self.audience)}",
            "X-Request-ID": current_request_id(),
            "X-Trace-ID": current_trace_id(),
            "Content-Type": "application/json",
        }
        if extra:
            headers.update(extra)
        return headers

    def _raise_for_response(self, response: httpx.Response) -> None:
        if response.is_success:
            return
        detail = None
        try:
            body = response.json()
            detail = body.get("detail") or body.get("message") or body.get("error")
        except Exception:
            detail = response.text[:500] if response.text else None
        if response.status_code == 404:
            raise NotFound(f"{self.service_name} resource not found", details=detail)
        if response.status_code == 429:
            raise RateLimited(f"{self.service_name} rate limit exceeded")
        if 400 <= response.status_code < 500:
            raise AppError(
                f"{self.service_name} rejected the request",
                status_code=response.status_code,
                code="upstream_rejected",
                details=detail,
            )
        raise UpstreamError(
            f"{self.service_name} is unavailable", service=self.service_name, details=detail
        )

    async def request(
        self,
        method: str,
        path: str,
        *,
        json: Any = None,
        params: dict[str, Any] | None = None,
        data: Any = None,
        files: Any = None,
        content: bytes | None = None,
        extra_headers: dict[str, str] | None = None,
        timeout: float | None = None,  # noqa: ASYNC109 - httpx per-request deadline
    ) -> httpx.Response:
        headers = self.headers(extra_headers)
        if files is not None or data is not None:
            headers.pop("Content-Type", None)
        try:
            response = await self._client.request(
                method,
                path,
                json=json,
                params=params,
                data=data,
                files=files,
                content=content,
                headers=headers,
                timeout=timeout,
            )
        except httpx.TimeoutException as exc:
            logger.warning("upstream_timeout", extra={"service": self.service_name, "path": path})
            raise UpstreamError(
                f"{self.service_name} timed out", service=self.service_name
            ) from exc
        except httpx.HTTPError as exc:
            logger.warning(
                "upstream_connection_error",
                extra={"service": self.service_name, "path": path, "error": str(exc)},
            )
            raise UpstreamError(
                f"{self.service_name} is unreachable", service=self.service_name
            ) from exc
        self._raise_for_response(response)
        return response

    async def health(self) -> bool:
        try:
            response = await self._client.get(
                "/internal/v1/health",
                headers=self.headers(),
                timeout=3.0,
            )
            return response.status_code < 500
        except Exception:
            return False
