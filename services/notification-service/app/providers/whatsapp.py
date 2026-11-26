"""WhatsApp Cloud API template provider."""

from __future__ import annotations

import logging

import httpx

from app.providers.base import DeliveryResult, WhatsAppMessage

logger = logging.getLogger(__name__)


class WhatsAppProvider:
    name = "whatsapp"

    def __init__(
        self,
        *,
        api_url: str,
        phone_number_id: str,
        access_token: str,
        template_name: str,
        template_language: str,
        timeout: float = 15.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.api_url = api_url.rstrip("/")
        self.phone_number_id = phone_number_id
        self.access_token = access_token
        self.template_name = template_name
        self.template_language = template_language
        self._client = client or httpx.AsyncClient(timeout=timeout)

    async def send(self, message: WhatsAppMessage) -> DeliveryResult:
        if not message.recipient:
            return DeliveryResult(
                success=False,
                error_code="missing_recipient",
                error_message="WhatsApp recipient is not available",
            )
        payload = {
            "messaging_product": "whatsapp",
            "to": message.recipient,
            "type": "template",
            "template": {
                "name": self.template_name,
                "language": {"code": self.template_language},
                "components": [
                    {
                        "type": "body",
                        "parameters": [
                            {"type": "text", "text": message.title},
                            {"type": "text", "text": message.body},
                        ],
                    }
                ],
            },
        }
        try:
            response = await self._client.post(
                f"{self.api_url}/{self.phone_number_id}/messages",
                headers={
                    "Authorization": f"Bearer {self.access_token}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
        except httpx.HTTPError as exc:
            logger.warning("whatsapp_transport_error", extra={"error": type(exc).__name__})
            return DeliveryResult(
                success=False,
                error_code="provider_unavailable",
                error_message=type(exc).__name__,
                retryable=True,
            )

        body = self._json(response)
        if response.is_success:
            messages = body.get("messages") or []
            provider_id = messages[0].get("id") if messages else None
            return DeliveryResult(
                success=True,
                provider_message_id=provider_id,
                http_status=response.status_code,
            )

        error = body.get("error") or {}
        message_text = str(error.get("message") or response.text[:500])
        retryable = response.status_code == 429 or response.status_code >= 500
        return DeliveryResult(
            success=False,
            error_code=str(error.get("code") or "provider_rejected"),
            error_message=message_text,
            retryable=retryable,
            retry_after_seconds=_retry_after(response),
            http_status=response.status_code,
        )

    @staticmethod
    def _json(response: httpx.Response) -> dict:
        try:
            return response.json()
        except Exception:
            return {}

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
