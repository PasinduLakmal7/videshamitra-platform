"""HTTP contract tests that do not need Postgres or Redis."""

from __future__ import annotations

from uuid import UUID

import httpx
import pytest

from app.api.dependencies import get_connection, get_current_user
from app.main import app
from app.models.entities import CurrentUser
from app.models.enums import UserRole

WORKER = CurrentUser(
    id=UUID("11111111-1111-1111-1111-111111111111"),
    role=UserRole.WORKER,
    preferred_language="en",
)
CASEWORKER = CurrentUser(
    id=UUID("22222222-2222-2222-2222-222222222222"),
    role=UserRole.CASEWORKER,
    preferred_language="en",
)


class DummyConn:
    async def fetch(self, *args, **kwargs):  # pragma: no cover
        return []

    async def fetchrow(self, *args, **kwargs):  # pragma: no cover
        return None

    async def fetchval(self, *args, **kwargs):  # pragma: no cover
        return None

    async def execute(self, *args, **kwargs):  # pragma: no cover
        return "OK"


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


@pytest.fixture(autouse=True)
def _reset_overrides():
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()


async def test_health() -> None:
    async with _client() as client:
        response = await client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.headers.get("X-Request-ID")


async def test_missing_token_returns_envelope() -> None:
    app.dependency_overrides[get_connection] = lambda: DummyConn()
    async with _client() as client:
        response = await client.get("/api/v1/users")
    assert response.status_code == 401
    body = response.json()
    assert body["error"]["code"] == "token_missing"
    assert body["meta"]["request_id"]


async def test_worker_forbidden_from_staff_route() -> None:
    app.dependency_overrides[get_connection] = lambda: DummyConn()
    app.dependency_overrides[get_current_user] = lambda: WORKER
    async with _client() as client:
        response = await client.get("/api/v1/users")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


async def test_caseworker_forbidden_from_admin_audit() -> None:
    app.dependency_overrides[get_connection] = lambda: DummyConn()
    app.dependency_overrides[get_current_user] = lambda: CASEWORKER
    async with _client() as client:
        response = await client.get("/api/v1/admin/audit-logs")
    assert response.status_code == 403


async def test_internal_route_rejects_missing_service_token() -> None:
    app.dependency_overrides[get_connection] = lambda: DummyConn()
    async with _client() as client:
        response = await client.get(
            "/internal/v1/documents/33333333-3333-3333-3333-333333333333/content"
        )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "service_token_missing"


async def test_unknown_route_uses_error_envelope() -> None:
    async with _client() as client:
        response = await client.get("/api/v1/nope")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


async def test_openapi_contract_has_required_paths() -> None:
    schema = app.openapi()
    paths = schema["paths"]
    required = [
        "/api/v1/auth/register",
        "/api/v1/auth/otp/verify",
        "/api/v1/users",
        "/api/v1/agencies",
        "/api/v1/verification",
        "/api/v1/documents",
        "/api/v1/migration/journeys",
        "/api/v1/checkins/{checkin_id}/respond",
        "/api/v1/complaints",
        "/api/v1/notifications",
        "/api/v1/admin/dashboard",
        "/api/v1/admin/cases/{case_id}/notes",
        "/api/v1/chat/sessions/{session_id}/messages",
        "/api/v1/webhooks/whatsapp",
        "/internal/v1/documents/{document_id}/content",
        "/internal/v1/agencies/{agency_id}/license-history",
    ]
    for path in required:
        assert path in paths, path
    assert schema["info"]["title"] == "VideshaMitra Core API"


async def test_idempotency_header_documented() -> None:
    operation = app.openapi()["paths"]["/api/v1/verification"]["post"]
    params = {param["name"] for param in operation.get("parameters", [])}
    assert "Idempotency-Key" in params
