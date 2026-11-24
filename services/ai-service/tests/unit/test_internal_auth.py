from __future__ import annotations

import time

import jwt
import pytest
from fastapi import Depends
from fastapi.testclient import TestClient

from app.core.internal_auth import create_core_token, require_core
from app.main import create_app
from tests.conftest import SECRET

PROBE = "/internal/v1/_probe"


@pytest.fixture
def client():
    app = create_app()

    @app.get(PROBE, dependencies=[Depends(require_core)])
    async def probe() -> dict[str, bool]:
        return {"ok": True}

    with TestClient(app) as test_client:
        yield test_client


def _call(client, token: str | None, scheme: str = "Bearer"):
    headers = {"Authorization": f"{scheme} {token}"} if token is not None else {}
    return client.get(PROBE, headers=headers)


def test_valid_token_accepted(client, core_token):
    response = _call(client, core_token())
    assert response.status_code == 200
    assert response.json() == {"ok": True}


@pytest.mark.parametrize(
    ("kwargs", "status", "code"),
    [
        ({"secret": "another-secret-that-is-long-enough-123"}, 401, "service_token_invalid"),
        ({"iat_offset": -600, "ttl": 60}, 401, "service_token_expired"),
        ({"aud": "core-api"}, 403, "service_token_audience"),
        ({"iss": "notification-service"}, 403, "service_token_issuer"),
        ({"ttl": 301}, 401, "service_token_lifetime"),
        ({"drop": ("iat",)}, 401, "service_token_invalid"),
        ({"drop": ("sub",)}, 401, "service_token_invalid"),
        ({"drop": ("exp",)}, 401, "service_token_invalid"),
    ],
)
def test_bad_tokens_rejected(client, core_token, kwargs, status, code):
    response = _call(client, core_token(**kwargs))
    assert response.status_code == status
    assert response.json()["error"]["code"] == code


def test_own_outbound_token_replayed_is_rejected(client):
    response = _call(client, create_core_token())
    assert response.status_code == 403
    assert response.json()["error"]["code"] in {"service_token_audience", "service_token_issuer"}


def test_missing_header_rejected(client):
    response = _call(client, None)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "service_token_missing"


def test_wrong_scheme_rejected(client, core_token):
    response = _call(client, core_token(), scheme="Basic")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "service_token_missing"


def test_garbage_token_rejected(client):
    response = _call(client, "not-a-jwt")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "service_token_invalid"


def test_none_algorithm_rejected(client):
    now = int(time.time())
    token = jwt.encode(
        {"iss": "core-api", "aud": "ai-service", "sub": "core-api", "iat": now, "exp": now + 60},
        None,
        algorithm="none",
    )
    assert _call(client, token).status_code == 401


def test_minted_token_for_core():
    claims = jwt.decode(create_core_token(), SECRET, algorithms=["HS256"], audience="core-api")
    assert claims["iss"] == "ai-service"
    assert claims["sub"] == "ai-service"
    assert claims["exp"] - claims["iat"] == 60
