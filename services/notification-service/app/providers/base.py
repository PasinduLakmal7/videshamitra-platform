"""Provider interfaces and delivery result types."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class PushMessage:
    token: str
    title: str
    body: str
    data: dict[str, str]
    notification_id: str


@dataclass(frozen=True)
class WhatsAppMessage:
    recipient: str
    title: str
    body: str
    locale: str
    notification_id: str


@dataclass
class DeliveryResult:
    success: bool
    provider_message_id: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    retryable: bool = False
    retry_after_seconds: int | None = None
    invalid_token: bool = False
    http_status: int | None = None


class PushProvider(Protocol):
    name: str

    async def send(self, message: PushMessage) -> DeliveryResult: ...

    async def aclose(self) -> None: ...


class WhatsAppProviderProtocol(Protocol):
    name: str

    async def send(self, message: WhatsAppMessage) -> DeliveryResult: ...

    async def aclose(self) -> None: ...
