"""Settings for ai-service, validated at startup."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["development", "test", "staging", "production"]

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
    # A service-local .env overrides the shared root one (it holds the ai_service_role DSN).
    model_config = SettingsConfigDict(
        env_file=("../../.env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    SERVICE_NAME: str = "ai-service"
    VERSION: str = "0.1.0"
    ENVIRONMENT: Environment = "production"
    LOG_LEVEL: str = "INFO"

    DATABASE_URL: str = ""
    # Admin DSN for migrations only; the runtime role has no CREATE on schema ai.
    MIGRATION_DATABASE_URL: str = ""
    DATABASE_MIN_POOL: int = Field(default=1, ge=1)
    DATABASE_MAX_POOL: int = Field(default=10, ge=1)
    DATABASE_COMMAND_TIMEOUT: float = Field(default=30.0, gt=0)
    REDIS_URL: str = "redis://localhost:6379/0"
    CORE_API_URL: str = "http://localhost:8000"

    INTERNAL_JWT_SECRET: SecretStr = Field(min_length=MIN_SECRET_LENGTH)

    GEMINI_API_KEY: SecretStr = SecretStr("")
    GEMINI_MODEL_FAST: str = "gemini-2.5-flash"
    GEMINI_MODEL_PRO: str = "gemini-2.5-pro"
    LLM_TIMEOUT_SECONDS: float = Field(default=30.0, gt=0)
    LLM_MAX_RETRIES: int = Field(default=2, ge=0, le=5)
    LLM_DAILY_TOKEN_BUDGET: int = Field(default=1_000_000, ge=0)

    FINGERPRINT_PEPPER: SecretStr = SecretStr("")

    WHATSAPP_ACCESS_TOKEN: SecretStr = SecretStr("")
    WHATSAPP_PHONE_NUMBER_ID: str = ""

    CHAT_RETENTION_DAYS: int = Field(default=30, ge=1)

    @model_validator(mode="after")
    def _reject_insecure_outside_dev(self) -> Settings:
        if self.is_dev:
            return self
        if _is_weak(self.INTERNAL_JWT_SECRET.get_secret_value()):
            raise ValueError(
                f"INTERNAL_JWT_SECRET is a placeholder or too weak for {self.ENVIRONMENT}"
            )
        if not self.GEMINI_API_KEY.get_secret_value():
            raise ValueError(f"GEMINI_API_KEY is required in {self.ENVIRONMENT}")
        if _is_weak(self.FINGERPRINT_PEPPER.get_secret_value()):
            raise ValueError(f"FINGERPRINT_PEPPER is missing or too weak for {self.ENVIRONMENT}")
        return self

    @property
    def is_dev(self) -> bool:
        return self.ENVIRONMENT in DEV_ENVIRONMENTS


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]


settings = get_settings()
