from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient

from app.api.dependencies import get_connection
from app.main import create_app


def _client() -> TestClient:
    app = create_app()

    async def fake_connection():
        yield None

    app.dependency_overrides[get_connection] = fake_connection
    return TestClient(app)


def test_health_and_internal_health_are_unauthenticated():
    client = _client()
    assert client.get("/health").json()["status"] == "ok"
    internal = client.get("/internal/v1/health")
    assert internal.status_code == 200
    assert internal.json()["scope"] == "internal"


def test_internal_routes_require_service_token():
    client = _client()
    response = client.get(f"/internal/v1/preferences/{uuid4()}")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "service_token_missing"


def test_device_payload_validation(core_token):
    client = _client()
    response = client.post(
        "/internal/v1/devices",
        headers={"Authorization": f"Bearer {core_token()}"},
        json={
            "user_id": str(uuid4()),
            "token": "token",
            "platform": "windows",
        },
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_preference_payload_validation(core_token):
    client = _client()
    response = client.put(
        f"/internal/v1/preferences/{uuid4()}",
        headers={"Authorization": f"Bearer {core_token()}"},
        json={"channels": {"fax": True}},
    )
    assert response.status_code == 422


def test_unknown_route_uses_error_envelope():
    client = _client()
    response = client.get("/internal/v1/nope")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"
