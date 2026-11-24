from __future__ import annotations

import re

from fastapi.testclient import TestClient

from app.main import app

PUBLIC_INTERNAL = {"/internal/v1/health"}
NIL_UUID = "00000000-0000-0000-0000-000000000000"


def test_every_internal_route_requires_core_token():
    paths = app.openapi()["paths"]
    assert PUBLIC_INTERNAL <= set(paths)
    with TestClient(app) as client:
        for path, operations in paths.items():
            assert path.startswith("/internal/v1/"), path
            if path in PUBLIC_INTERNAL:
                continue
            url = re.sub(r"\{[^}]+\}", NIL_UUID, path)
            for method in operations:
                response = client.request(method.upper(), url)
                assert response.status_code == 401, f"{method.upper()} {path}"
                assert response.json()["error"]["code"] == "service_token_missing"
