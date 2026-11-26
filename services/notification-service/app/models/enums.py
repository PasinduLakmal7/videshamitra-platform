"""Notification domain enums and channel defaults."""

from __future__ import annotations

from enum import StrEnum


class Platform(StrEnum):
    ANDROID = "android"
    IOS = "ios"
    WEB = "web"


class DeliveryChannel(StrEnum):
    PUSH = "push"
    WHATSAPP = "whatsapp"
    EMAIL = "email"
    SMS = "sms"


class DeliveryStatus(StrEnum):
    PENDING = "pending"
    SENDING = "sending"
    SENT = "sent"
    FAILED = "failed"
    SKIPPED = "skipped"


class PendingReason(StrEnum):
    NEW = "new"
    RETRY = "retry"
    QUIET_HOURS = "quiet_hours"


class AttemptStatus(StrEnum):
    SENT = "sent"
    RETRYABLE = "retryable"
    PERMANENT = "permanent"


class ProviderName(StrEnum):
    STUB = "stub"
    FCM = "fcm"
    WHATSAPP = "whatsapp"


DEFAULT_CHANNELS: dict[str, bool] = {
    "push": True,
    "whatsapp": False,
    "email": False,
    "sms": False,
}

SUPPORTED_CHANNELS = frozenset({"push", "whatsapp", "email", "sms"})
