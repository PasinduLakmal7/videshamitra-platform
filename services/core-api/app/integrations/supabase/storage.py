"""Supabase Storage client for the private documents bucket."""

from __future__ import annotations

import logging
from urllib.parse import quote

import httpx

from app.core.config import settings
from app.core.exceptions import NotFound, ServiceUnavailable, UpstreamError

logger = logging.getLogger(__name__)


class SupabaseStorage:
    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client or httpx.AsyncClient(timeout=settings.SUPABASE_TIMEOUT_SECONDS)

    async def aclose(self) -> None:
        await self._client.aclose()

    def _require_config(self) -> None:
        if not settings.supabase_admin_configured:
            raise ServiceUnavailable(
                "Supabase Storage is not configured", code="storage_not_configured"
            )

    def _headers(self) -> dict[str, str]:
        return {
            "apikey": settings.SUPABASE_SERVICE_ROLE_KEY,
            "Authorization": f"Bearer {settings.SUPABASE_SERVICE_ROLE_KEY}",
        }

    def _object_url(self, path: str, *, authenticated: bool = False) -> str:
        prefix = "object/authenticated" if authenticated else "object"
        return (
            f"{settings.storage_internal_base_url}/{prefix}/"
            f"{quote(settings.DOCUMENTS_BUCKET, safe='')}/{quote(path, safe='/')}"
        )

    async def upload(self, path: str, content: bytes, content_type: str) -> None:
        self._require_config()
        headers = {
            **self._headers(),
            "Content-Type": content_type,
            "x-upsert": "false",
            "Cache-Control": "no-store",
        }
        try:
            response = await self._client.post(
                self._object_url(path), content=content, headers=headers
            )
        except httpx.HTTPError as exc:
            raise UpstreamError("Storage upload failed", service="supabase-storage") from exc
        if response.status_code >= 400:
            logger.error(
                "storage_upload_failed",
                extra={"status": response.status_code, "path": path},
            )
            raise UpstreamError("Storage upload failed", service="supabase-storage")

    async def download(self, path: str) -> bytes:
        self._require_config()
        try:
            response = await self._client.get(
                self._object_url(path, authenticated=True), headers=self._headers()
            )
        except httpx.HTTPError as exc:
            raise UpstreamError("Storage download failed", service="supabase-storage") from exc
        if response.status_code == 404:
            raise NotFound("Document content not found", code="document_content_missing")
        if response.status_code >= 400:
            raise UpstreamError("Storage download failed", service="supabase-storage")
        return response.content

    async def signed_url(self, path: str, expires_in: int) -> str:
        self._require_config()
        url = (
            f"{settings.storage_internal_base_url}/object/sign/"
            f"{quote(settings.DOCUMENTS_BUCKET, safe='')}/{quote(path, safe='/')}"
        )
        try:
            response = await self._client.post(
                url, json={"expiresIn": expires_in}, headers=self._headers()
            )
        except httpx.HTTPError as exc:
            raise UpstreamError("Could not sign storage URL", service="supabase-storage") from exc
        if response.status_code == 404:
            raise NotFound("Document content not found", code="document_content_missing")
        if response.status_code >= 400:
            raise UpstreamError("Could not sign storage URL", service="supabase-storage")
        payload = response.json()
        signed = payload.get("signedURL") or payload.get("signedUrl")
        if not signed:
            raise UpstreamError("Storage returned no signed URL", service="supabase-storage")
        if signed.startswith("http"):
            return signed
        return f"{settings.storage_public_base_url}{signed}"

    async def remove(self, path: str) -> None:
        self._require_config()
        try:
            response = await self._client.delete(
                f"{settings.storage_internal_base_url}/object/"
                f"{quote(settings.DOCUMENTS_BUCKET, safe='')}",
                json={"prefixes": [path]},
                headers=self._headers(),
            )
        except httpx.HTTPError:
            logger.warning("storage_delete_failed", extra={"path": path})
            return
        if response.status_code >= 400:
            logger.warning(
                "storage_delete_failed",
                extra={"path": path, "status": response.status_code},
            )

    async def health(self) -> bool:
        if not settings.supabase_admin_configured:
            return False
        try:
            response = await self._client.get(
                f"{settings.storage_internal_base_url}/bucket/"
                f"{quote(settings.DOCUMENTS_BUCKET, safe='')}",
                headers=self._headers(),
                timeout=3.0,
            )
            return response.status_code < 400
        except Exception:
            return False
