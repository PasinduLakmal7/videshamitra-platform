"""Application settings for core-api.

All configuration comes from the environment (or a local .env file).  The two
hard requirements are a database DSN and the internal service JWT secret; the
process fails fast if either is missing.
"""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["development", "test", "staging", "production"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Service ---------------------------------------------------------
    PROJECT_NAME: str = "VideshaMitra Core API"
    SERVICE_NAME: str = "core-api"
    VERSION: str = "0.1.0"
    API_V1_STR: str = "/api/v1"
    ENVIRONMENT: Environment = "development"
    LOG_LEVEL: str = "INFO"
    CORS_ORIGINS: list[str] = Field(
        default_factory=lambda: ["http://localhost:5173", "http://localhost:5174"]
    )

    # --- Database --------------------------------------------------------
    DATABASE_URL: str
    DATABASE_MIN_POOL: int = Field(default=2, ge=1)
    DATABASE_MAX_POOL: int = Field(default=10, ge=1)
    DATABASE_COMMAND_TIMEOUT: float = 30.0

    # --- Supabase --------------------------------------------------------
    SUPABASE_URL: str = ""
    SUPABASE_INTERNAL_URL: str = ""
    SUPABASE_ANON_KEY: str = ""
    SUPABASE_SERVICE_ROLE_KEY: str = ""
    SUPABASE_JWT_SECRET: str = ""
    SUPABASE_JWKS_URL: str = ""
    SUPABASE_TIMEOUT_SECONDS: float = 15.0
    JWT_AUDIENCE: str = "authenticated"
    JWT_ISSUER: str = ""

    # --- Auth fallbacks / limits ----------------------------------------
    OTP_RATE_LIMIT_PER_10_MIN: int = 5
    AUTH_DEV_OTP: str = ""

    # --- Redis / events --------------------------------------------------
    REDIS_URL: str = "redis://localhost:6379/0"
    INTERNAL_JWT_SECRET: str = Field(min_length=16)
    INTERNAL_JWT_ISSUER: str = "core-api"
    INTERNAL_JWT_AUDIENCE: str = "core-api"
    INTERNAL_ALLOWED_ISSUERS: list[str] = Field(
        default_factory=lambda: ["ai-service", "notification-service"]
    )
    INTERNAL_JWT_TTL_SECONDS: int = Field(default=300, ge=30, le=300)
    OUTBOX_BATCH_SIZE: int = 50
    OUTBOX_MAX_ATTEMPTS: int = 10
    EVENT_MAX_LENGTH: int = 100_000

    # --- Internal services ----------------------------------------------
    AI_SERVICE_URL: str = "http://ai-service:8010"
    NOTIFICATION_SERVICE_URL: str = "http://notification-service:8020"
    INTERNAL_HTTP_TIMEOUT_SECONDS: float = 15.0

    # --- Documents -------------------------------------------------------
    DOCUMENTS_BUCKET: str = "documents"
    MAX_UPLOAD_MB: int = 25
    MAX_PDF_PAGES: int = 50
    SIGNED_URL_TTL_SECONDS: int = 300
    MAX_AUDIO_MB: int = 10

    # --- Domain workers --------------------------------------------------
    CHECKIN_GRACE_HOURS: int = 72
    STALE_PROCESSING_MINUTES: int = 15
    AGENCY_MONITOR_INTERVAL_SECONDS: int = 3600
    CHECKIN_SCHEDULER_INTERVAL_SECONDS: int = 60
    IDEMPOTENCY_TTL_HOURS: int = 24

    # --- SLBFE -----------------------------------------------------------
    SLBFE_SOURCE_URL: str = ""
    SLBFE_API_KEY: str = ""

    # --- WhatsApp webhook ------------------------------------------------
    WHATSAPP_APP_SECRET: str = ""
    WHATSAPP_VERIFY_TOKEN: str = ""

    # --- Kafka-style stream names ---------------------------------------
    AI_REQUESTS_STREAM: str = "vm:ai:requests"
    AI_RESULTS_STREAM: str = "vm:ai:results"
    NOTIFICATION_REQUESTS_STREAM: str = "vm:notifications:requests"
    NOTIFICATION_RESULTS_STREAM: str = "vm:notifications:results"
    AI_CONSUMER_GROUP: str = "core-api"

    @field_validator("CORS_ORIGINS", "INTERNAL_ALLOWED_ISSUERS", mode="before")
    @classmethod
    def _split_list(cls, value: object) -> object:
        if isinstance(value, str):
            value = value.strip()
            if not value:
                return []
            if value.startswith("["):
                return json.loads(value)
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"

    @property
    def supabase_api_url(self) -> str:
        """Server-to-server Supabase URL (Docker uses host.docker.internal)."""
        return (self.SUPABASE_INTERNAL_URL or self.SUPABASE_URL).rstrip("/")

    @property
    def supabase_jwks_url(self) -> str:
        if self.SUPABASE_JWKS_URL:
            return self.SUPABASE_JWKS_URL
        if self.supabase_api_url:
            return f"{self.supabase_api_url}/auth/v1/.well-known/jwks.json"
        return ""

    @property
    def jwt_issuer(self) -> str:
        if self.JWT_ISSUER:
            return self.JWT_ISSUER
        if self.SUPABASE_URL:
            return f"{self.SUPABASE_URL.rstrip('/')}/auth/v1"
        return ""

    @property
    def supabase_configured(self) -> bool:
        return bool(self.supabase_api_url and self.SUPABASE_ANON_KEY)

    @property
    def supabase_admin_configured(self) -> bool:
        return bool(self.supabase_api_url and self.SUPABASE_SERVICE_ROLE_KEY)

    @property
    def storage_internal_base_url(self) -> str:
        return f"{self.supabase_api_url}/storage/v1"

    @property
    def storage_public_base_url(self) -> str:
        """Base used when returning signed URLs to browsers/mobile clients."""
        return f"{(self.SUPABASE_URL or self.supabase_api_url).rstrip('/')}/storage/v1"

    @property
    def max_upload_bytes(self) -> int:
        return self.MAX_UPLOAD_MB * 1024 * 1024

    @property
    def max_audio_bytes(self) -> int:
        return self.MAX_AUDIO_MB * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]


settings = get_settings()
