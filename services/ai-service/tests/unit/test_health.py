from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app


def test_health_needs_no_auth_and_echoes_ids():
    with TestClient(create_app()) as client:
        response = client.get(
            "/internal/v1/health", headers={"X-Request-ID": "req-1", "X-Trace-ID": "trace-1"}
        )
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["X-Request-ID"] == "req-1"
    assert response.headers["X-Trace-ID"] == "trace-1"


def test_request_id_generated_when_missing():
    with TestClient(create_app()) as client:
        response = client.get("/internal/v1/health")
    assert response.headers["X-Request-ID"]
    assert response.headers["X-Trace-ID"] == response.headers["X-Request-ID"]


def test_unknown_route_uses_error_envelope():
    with TestClient(create_app()) as client:
        response = client.get("/internal/v1/nope", headers={"X-Request-ID": "req-2"})
    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "not_found"
    assert body["meta"]["request_id"] == "req-2"
