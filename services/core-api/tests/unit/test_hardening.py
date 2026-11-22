"""Regression tests for the security audit fixes."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import httpx
import jwt
import pytest
import respx
from pydantic import ValidationError

from app.core.config import Settings, settings
from app.core.exceptions import (
    Forbidden,
    NotFound,
    RateLimited,
    ServiceUnavailable,
    Unauthorized,
)
from app.core.internal_auth import require_service_from, verify_service_token
from app.integrations.slbfe.client import fetch_source
from app.models.entities import RequestInfo
from app.repositories.migration_repository import MigrationRepository
from app.schemas.agency import AgencyImportRequest
from app.schemas.auth import OtpRequest, OtpVerifyRequest
from app.schemas.chat import ChatMessageCreate
from app.services import auth_service as auth_module
from app.services.auth_service import AuthService
from app.services.chat_service import ChatService
from app.services.verification_service import VerificationService

STRONG = "x" * 48
REQUEST = RequestInfo(ip_address="203.0.113.7", user_agent="pytest")


def _settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "_env_file": None,
        "DATABASE_URL": "postgresql://localhost/test",
        "INTERNAL_JWT_SECRET": STRONG,
        "SUPABASE_JWT_SECRET": "",
        "AUTH_DEV_OTP": "",
    }
    values.update(overrides)
    return Settings(**values)


def test_environment_defaults_to_production(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    assert _settings().ENVIRONMENT == "production"


@pytest.mark.parametrize(
    "overrides",
    [
        {"AUTH_DEV_OTP": "123456"},
        {"SUPABASE_JWT_SECRET": "super-secret-jwt-token-with-at-least-32-characters-long"},
        {"INTERNAL_JWT_SECRET": "replace-with-a-long-random-internal-secret-value"},
        {"SUPABASE_JWT_SECRET": "too-short"},
    ],
)
def test_insecure_values_rejected_outside_dev(overrides: dict[str, str]) -> None:
    with pytest.raises(ValidationError):
        _settings(ENVIRONMENT="staging", **overrides)


def test_dev_values_allowed_in_development() -> None:
    cfg = _settings(
        ENVIRONMENT="development",
        AUTH_DEV_OTP="123456",
        SUPABASE_JWT_SECRET="super-secret-jwt-token-with-at-least-32-characters-long",
    )
    assert cfg.is_dev


def test_internal_secret_needs_32_chars() -> None:
    with pytest.raises(ValidationError):
        _settings(ENVIRONMENT="development", INTERNAL_JWT_SECRET="sixteen-chars-ok")


def _service_token(iss: str, *, lifetime: int = 60, include_iat: bool = True) -> str:
    now = int(datetime.now(UTC).timestamp())
    claims: dict[str, Any] = {"iss": iss, "aud": "core-api", "sub": iss, "exp": now + lifetime}
    if include_iat:
        claims["iat"] = now
    return jwt.encode(claims, settings.INTERNAL_JWT_SECRET, algorithm="HS256")


def test_service_token_lifetime_capped() -> None:
    with pytest.raises(Unauthorized) as exc:
        verify_service_token(_service_token("ai-service", lifetime=3600))
    assert exc.value.code == "service_token_lifetime"


def test_service_token_requires_iat() -> None:
    with pytest.raises(Unauthorized):
        verify_service_token(_service_token("ai-service", include_iat=False))


async def test_ai_only_routes_reject_other_services() -> None:
    dependency = require_service_from("ai-service")
    ok_request = SimpleNamespace(
        headers={"Authorization": f"Bearer {_service_token('ai-service')}"}
    )
    identity = await dependency(ok_request)  # type: ignore[arg-type]
    assert identity.service == "ai-service"
    bad_request = SimpleNamespace(
        headers={"Authorization": f"Bearer {_service_token('notification-service')}"}
    )
    with pytest.raises(Forbidden):
        await dependency(bad_request)  # type: ignore[arg-type]


def test_client_ip_uses_last_forwarded_hop() -> None:
    request = SimpleNamespace(
        headers={"X-Forwarded-For": "1.2.3.4, 198.51.100.9", "User-Agent": "ua"},
        client=SimpleNamespace(host="10.0.0.2"),
    )
    assert RequestInfo.from_request(request).ip_address == "198.51.100.9"


class _BrokenRedis:
    def pipeline(self) -> Any:
        raise ConnectionError("redis down")


class _CountingPipe:
    def __init__(self, count: int) -> None:
        self.count = count

    def incr(self, key: str) -> None: ...

    def expire(self, key: str, seconds: int) -> None: ...

    async def execute(self) -> list[int]:
        return [self.count, 1, self.count, 1]


class _CountingRedis:
    def __init__(self, count: int) -> None:
        self.count = count

    def pipeline(self) -> _CountingPipe:
        return _CountingPipe(self.count)


async def test_rate_limit_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(auth_module.redis_db, "get_client", lambda: _BrokenRedis())
    service = AuthService(client=object())  # type: ignore[arg-type]
    with pytest.raises(ServiceUnavailable):
        await service._rate_limit(scope="otp", ip="1.1.1.1", subject="+94770000000", limit=5)
    await service._rate_limit(
        scope="login", ip="1.1.1.1", subject="a@b.c", limit=5, fail_closed=False
    )


async def test_rate_limit_blocks_over_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(auth_module.redis_db, "get_client", lambda: _CountingRedis(6))
    service = AuthService(client=object())  # type: ignore[arg-type]
    with pytest.raises(RateLimited):
        await service._rate_limit(scope="otp", ip="1.1.1.1", subject="+94770000000", limit=5)


class _FakeAuthClient:
    async def request_otp(self, **_: Any) -> dict[str, Any]:
        return {}


class _FakeUsers:
    def __init__(self, profile: dict[str, Any] | None) -> None:
        self.profile = profile

    async def get_by_phone(self, conn: Any, phone: str) -> dict[str, Any] | None:
        return self.profile


class _FakeAudit:
    def __init__(self) -> None:
        self.actions: list[str] = []

    async def record(self, conn: Any, **kwargs: Any) -> None:
        self.actions.append(kwargs["action"])


def _profile(role: str, *, active: bool = True) -> dict[str, Any]:
    return {
        "id": uuid4(),
        "role": role,
        "full_name": "Test",
        "phone": "+94770000001",
        "preferred_language": "en",
        "country_of_work": None,
        "is_active": active,
        "created_at": datetime.now(UTC),
    }


def _dev_auth(monkeypatch: pytest.MonkeyPatch, profile: dict[str, Any] | None) -> AuthService:
    monkeypatch.setattr(settings, "AUTH_DEV_OTP", "246810")
    monkeypatch.setattr(settings, "SUPABASE_SERVICE_ROLE_KEY", "service-role")

    async def no_limit(*_: Any, **__: Any) -> None:
        return None

    service = AuthService(
        client=_FakeAuthClient(),  # type: ignore[arg-type]
        users=_FakeUsers(profile),  # type: ignore[arg-type]
        audit=_FakeAudit(),  # type: ignore[arg-type]
    )
    monkeypatch.setattr(service, "_rate_limit", no_limit)
    return service


async def test_request_otp_never_returns_code(monkeypatch: pytest.MonkeyPatch) -> None:
    service = _dev_auth(monkeypatch, None)
    result = await service.request_otp(
        None,  # type: ignore[arg-type]
        payload=OtpRequest(phone="+94770000001"),
        request=REQUEST,
    )
    assert "dev_otp" not in result


@pytest.mark.parametrize("role", ["admin", "caseworker"])
async def test_dev_otp_refuses_staff(monkeypatch: pytest.MonkeyPatch, role: str) -> None:
    service = _dev_auth(monkeypatch, _profile(role))
    with pytest.raises(Unauthorized) as exc:
        await service.verify_otp(
            None,  # type: ignore[arg-type]
            payload=OtpVerifyRequest(phone="+94770000001", token="246810"),
            request=REQUEST,
        )
    assert exc.value.code == "dev_otp_forbidden"


async def test_dev_otp_logs_in_worker_with_audit(monkeypatch: pytest.MonkeyPatch) -> None:
    service = _dev_auth(monkeypatch, _profile("worker"))
    session = await service.verify_otp(
        None,  # type: ignore[arg-type]
        payload=OtpVerifyRequest(phone="+94770000001", token="246810"),
        request=REQUEST,
    )
    assert session.access_token
    assert service.audit.actions == ["auth.dev_otp_login"]  # type: ignore[attr-defined]


class _Tx:
    async def __aenter__(self) -> None:
        return None

    async def __aexit__(self, *_: Any) -> None:
        return None


class _TxConn:
    def transaction(self) -> _Tx:
        return _Tx()


class _StaleRepo:
    def __init__(self, row: dict[str, Any]) -> None:
        self.row = row
        self.failed: list[UUID] = []
        self.retried: list[UUID] = []

    async def stale_in_flight(self, conn: Any, *, minutes: int) -> list[dict[str, Any]]:
        return [self.row]

    async def apply_failure(self, conn: Any, *, verification_id: UUID, **_: Any) -> dict:
        self.failed.append(verification_id)
        return self.row

    async def mark_retry(self, conn: Any, verification_id: UUID) -> None:
        self.retried.append(verification_id)
        return None


async def test_stale_verification_fails_after_retry_cap() -> None:
    row = {"id": uuid4(), "retry_count": settings.MAX_VERIFICATION_RETRIES}
    repo = _StaleRepo(row)
    audit = _FakeAudit()
    service = VerificationService(repo=repo, audit=audit)  # type: ignore[arg-type]
    await service.recover_stale(_TxConn())  # type: ignore[arg-type]
    assert repo.failed == [row["id"]]
    assert repo.retried == []
    assert audit.actions == ["verification.stale_failed"]


async def test_stale_verification_retried_below_cap() -> None:
    row = {"id": uuid4(), "retry_count": 0}
    repo = _StaleRepo(row)
    service = VerificationService(repo=repo, audit=_FakeAudit())  # type: ignore[arg-type]
    await service.recover_stale(_TxConn())  # type: ignore[arg-type]
    assert repo.retried == [row["id"]]
    assert repo.failed == []


class _SqlCapture:
    def __init__(self) -> None:
        self.sql: list[str] = []

    async def fetch(self, sql: str, *args: Any) -> list[Any]:
        self.sql.append(sql)
        return []


async def test_checkin_queries_respect_consent() -> None:
    conn = _SqlCapture()
    repo = MigrationRepository()
    await repo.due_checkins(conn)  # type: ignore[arg-type]
    await repo.missed_checkins(conn, grace_hours=72)  # type: ignore[arg-type]
    assert all("j.consent_checkins" in sql for sql in conn.sql)


def test_agency_import_rejects_client_source() -> None:
    assert "source" not in AgencyImportRequest.model_fields


@respx.mock
async def test_slbfe_key_not_sent_to_foreign_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "SLBFE_SOURCE_URL", "https://slbfe.example/agencies.json")
    monkeypatch.setattr(settings, "SLBFE_API_KEY", "secret-key")
    route = respx.get("https://other.example/data.json").mock(
        return_value=httpx.Response(200, content=b"[]")
    )
    await fetch_source("https://other.example/data.json")
    assert "Authorization" not in route.calls.last.request.headers


def test_chat_attachments_must_be_uuids() -> None:
    with pytest.raises(ValidationError):
        ChatMessageCreate(content="hi", attachments=["../../internal"])


class _Documents:
    def __init__(self, owned: set[UUID]) -> None:
        self.owned = owned

    async def owned_ids(self, conn: Any, *, user_id: UUID, document_ids: list[UUID]) -> set:
        return self.owned & set(document_ids)


async def test_chat_rejects_foreign_attachments() -> None:
    mine, theirs = uuid4(), uuid4()
    actor = SimpleNamespace(id=uuid4())
    service = ChatService(client=object(), documents=_Documents({mine}))  # type: ignore[arg-type]
    await service.check_attachments(None, actor, [mine])  # type: ignore[arg-type]
    with pytest.raises(NotFound):
        await service.check_attachments(None, actor, [mine, theirs])  # type: ignore[arg-type]
