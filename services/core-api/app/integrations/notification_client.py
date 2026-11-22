"""Client for notification-service device/preference APIs.

core-api never stores tokens or preferences; it validates the caller and
forwards with a service JWT.
"""

from __future__ import annotations

from typing import Any

import httpx

from app.integrations.base import BaseServiceClient


class NotificationClient(BaseServiceClient):
    def __init__(
        self,
        base_url: str,
        *,
        timeout: float | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(
            base_url,
            service_name="notification-service",
            audience="notification-service",
            timeout=timeout,
            client=client,
        )

    async def register_device(self, payload: dict[str, Any]) -> dict[str, Any]:
        response = await self.request("POST", "/internal/v1/devices", json=payload)
        return response.json()

    async def unregister_device(self, token: str, user_id: str) -> dict[str, Any]:
        from urllib.parse import quote

        response = await self.request(
            "DELETE",
            f"/internal/v1/devices/{quote(token, safe='')}",
            params={"user_id": user_id},
        )
        return response.json() if response.content else {"message": "unregistered"}

    async def get_preferences(self, user_id: str) -> dict[str, Any]:
        response = await self.request("GET", f"/internal/v1/preferences/{user_id}")
        return response.json()

    async def update_preferences(self, user_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        response = await self.request("PUT", f"/internal/v1/preferences/{user_id}", json=payload)
        return response.json()
