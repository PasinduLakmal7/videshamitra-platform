"""Deterministic provider for local development and CI."""

from __future__ import annotations

from uuid import uuid4

from app.providers.base import DeliveryResult, PushMessage


class StubPushProvider:
    name = "stub"

    def __init__(self, failure_mode: str = "success") -> None:
        self.failure_mode = failure_mode

    async def send(self, message: PushMessage) -> DeliveryResult:
        if self.failure_mode == "retryable":
            return DeliveryResult(
                success=False,
                error_code="stub_retryable",
                error_message="stub requested a retry",
                retryable=True,
            )
        if self.failure_mode == "permanent":
            return DeliveryResult(
                success=False,
                error_code="stub_permanent",
                error_message="stub requested a permanent failure",
            )
        if self.failure_mode == "invalid_token":
            return DeliveryResult(
                success=False,
                error_code="device_unregistered",
                error_message="stub requested token pruning",
                invalid_token=True,
            )
        return DeliveryResult(
            success=True,
            provider_message_id=f"stub-{uuid4()}",
        )

    async def aclose(self) -> None:
        return None
