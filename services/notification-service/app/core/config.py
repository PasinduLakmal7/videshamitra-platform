"""Settings for notification-service, validated at startup."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["development", "test", "staging", "production"]
PushProvider = Literal["stub", "fcm"]
StubFailureMode = Literal["success", "retryable", "permanent", "invalid_token"]

DEV_ENVIRONMENTS = frozenset({"development", "test"})
MIN_SECRET_LENGTH = 32
KNOWN_INSECURE_SECRETS = frozenset(
    {
        "super-secret-jwt-token-with-at-least-32-characters-long",
        "replace-with-a-long-random-internal-secret",
    }
)


def _is_weak(value: str) -> bool:
    return (
        value in KNOWN_INSECURE_SECRETS
        or value.startswith("replace-with")
        or len(value) < MIN_SECRET_LENGTH
    )


class Settings(BaseSettings):
    # A service-local .env overrides the shared root one (it holds the
    # notification_service_role DSN).
    model_config = SettingsConfigDict(
        env_file=("../../.env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    SERVICE_NAME: str = "notification-service"
    VERSION: str = "0.1.0"
    PROJECT_NAME: str = "VideshaMitra Notification Service"
    ENVIRONMENT: Environment = "production"
    LOG_LEVEL: str = "INFO"

    DATABASE_URL: str = ""
    MIGRATION_DATABASE_URL: str = ""
    DATABASE_MIN_POOL: int = Field(default=2, ge=1)
    DATABASE_MAX_POOL: int = Field(default=10, ge=1)
    DATABASE_COMMAND_TIMEOUT: float = Field(default=30.0, gt=0)

    REDIS_URL: str = "redis://localhost:6379/0"
    EVENT_MAX_LENGTH: int = Field(default=100_000, ge=1)

    INTERNAL_JWT_SECRET: SecretStr = Field(min_length=MIN_SECRET_LENGTH)

    NOTIFICATION_REQUESTS_STREAM: str = "vm:notifications:requests"
    NOTIFICATION_RESULTS_STREAM: str = "vm:notifications:results"
    NOTIFICATION_CONSUMER_GROUP: str = "notification-service"
    NOTIFICATION_CONSUMER_BATCH: int = Field(default=10, ge=1, le=100)
    NOTIFICATION_DLQ_SUFFIX: str = ":dlq"

    QUIET_HOURS_TIMEZONE: str = "Asia/Colombo"
    MAX_DEVICES_PER_USER: int = Field(default=10, ge=1)

    PUSH_PROVIDER: PushProvider = "stub"
    FCM_PROJECT_ID: str = ""
    FCM_SERVICE_ACCOUNT_FILE: str = ""
    FCM_SERVICE_ACCOUNT_JSON: SecretStr = SecretStr("")
    FCM_API_URL: str = "https://fcm.googleapis.com"
    FCM_TIMEOUT_SECONDS: float = Field(default=15.0, gt=0)

    WHATSAPP_ENABLED: bool = False
    WHATSAPP_API_URL: str = "https://graph.facebook.com/v21.0"
    WHATSAPP_PHONE_NUMBER_ID: str = ""
    WHATSAPP_ACCESS_TOKEN: SecretStr = SecretStr("")
    WHATSAPP_TEMPLATE_NAME: str = "notification_generic"
    WHATSAPP_TEMPLATE_LANGUAGE: str = "en"
    WHATSAPP_TIMEOUT_SECONDS: float = Field(default=15.0, gt=0)

    DELIVERY_MAX_ATTEMPTS: int = Field(default=6, ge=1, le=20)
    DELIVERY_BASE_BACKOFF_SECONDS: int = Field(default=30, ge=1)
    DELIVERY_MAX_BACKOFF_SECONDS: int = Field(default=3600, ge=1)
    DELIVERY_POLL_INTERVAL_SECONDS: float = Field(default=2.0, gt=0)
    DELIVERY_BATCH_SIZE: int = Field(default=50, ge=1, le=500)
    SENDING_TIMEOUT_SECONDS: int = Field(default=300, ge=30)
    STUB_FAILURE_MODE: StubFailureMode = "success"

    @field_validator("QUIET_HOURS_TIMEZONE")
    @classmethod
    def _valid_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"Unknown timezone: {value}") from exc
        return value

    @model_validator(mode="after")
    def _validate(self) -> Settings:
        if not self.DATABASE_URL:
            raise ValueError("DATABASE_URL is required")
        if self.PUSH_PROVIDER == "fcm" and not self.FCM_PROJECT_ID:
            raise ValueError("FCM_PROJECT_ID is required when PUSH_PROVIDER=fcm")
        if self.PUSH_PROVIDER == "fcm" and not (
            self.FCM_SERVICE_ACCOUNT_FILE or self.FCM_SERVICE_ACCOUNT_JSON.get_secret_value()
        ):
            raise ValueError(
                "FCM_SERVICE_ACCOUNT_FILE or FCM_SERVICE_ACCOUNT_JSON is required "
                "when PUSH_PROVIDER=fcm"
            )
        if self.WHATSAPP_ENABLED:
            missing = [name for name in ("WHATSAPP_PHONE_NUMBER_ID",) if not getattr(self, name)]
            if not self.WHATSAPP_ACCESS_TOKEN.get_secret_value():
                missing.append("WHATSAPP_ACCESS_TOKEN")
            if missing:
                raise ValueError(f"WhatsApp is enabled but missing: {', '.join(missing)}")
        if self.is_dev:
            return self
        if _is_weak(self.INTERNAL_JWT_SECRET.get_secret_value()):
            raise ValueError(
                f"INTERNAL_JWT_SECRET is a placeholder or too weak for {self.ENVIRONMENT}"
            )
        if self.PUSH_PROVIDER == "stub":
            raise ValueError("PUSH_PROVIDER=stub is only allowed in development/test")
        return self

    @property
    def is_dev(self) -> bool:
        return self.ENVIRONMENT in DEV_ENVIRONMENTS


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]


settings = get_settings()
