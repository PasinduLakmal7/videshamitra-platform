from __future__ import annotations

from uuid import uuid4

import httpx
import jwt
import pytest
import respx

from app.clients.core_api import CoreApiClient
from app.core.errors import NotFound, UpstreamError
from app.core.request_id import request_id_var, trace_id_var
from tests.conftest import SECRET

BASE = "http://core-api.test"


@pytest.fixture
async def client():
    core = CoreApiClient(BASE)
    yield core
    await core.aclose()


@respx.mock
async def test_sends_fresh_service_token_and_trace_headers(client):
    vid = uuid4()
    route = respx.get(f"{BASE}/internal/v1/verifications/{vid}").respond(
        json={"data": {"verification": {"id": str(vid)}, "documents": []}, "meta": {}}
    )
    rid = request_id_var.set("req-1")
    tid = trace_id_var.set("trace-1")
    try:
        data = await client.get_verification(vid)
    finally:
        request_id_var.reset(rid)
        trace_id_var.reset(tid)

    assert data == {"verification": {"id": str(vid)}, "documents": []}
    headers = route.calls.last.request.headers
    assert headers["X-Request-ID"] == "req-1"
    assert headers["X-Trace-ID"] == "trace-1"
    claims = jwt.decode(
        headers["Authorization"].removeprefix("Bearer "),
        SECRET,
        algorithms=["HS256"],
        audience="core-api",
    )
    assert claims["iss"] == "ai-service"
    assert claims["sub"] == "ai-service"
    assert claims["exp"] - claims["iat"] == 60


@respx.mock
async def test_document_bytes_and_mime(client):
    did = uuid4()
    respx.get(f"{BASE}/internal/v1/documents/{did}/content").respond(
        content=b"%PDF-1.7", headers={"content-type": "application/pdf"}
    )
    content, mime = await client.get_document_bytes(did)
    assert content == b"%PDF-1.7"
    assert mime == "application/pdf"


@respx.mock
async def test_license_history_unwrapped(client):
    aid = uuid4()
    respx.get(f"{BASE}/internal/v1/agencies/{aid}/license-history").respond(
        json={"data": {"agency": {"id": str(aid)}, "licenses": []}}
    )
    assert (await client.get_license_history(aid))["licenses"] == []


@respx.mock
async def test_not_found_maps_to_not_found(client):
    respx.get(url__startswith=f"{BASE}/internal/v1/verifications/").respond(404)
    with pytest.raises(NotFound):
        await client.get_verification(uuid4())


@respx.mock
async def test_server_error_maps_to_upstream(client):
    respx.get(url__startswith=f"{BASE}/internal/v1/verifications/").respond(500)
    with pytest.raises(UpstreamError):
        await client.get_verification(uuid4())


@respx.mock
async def test_get_retries_transport_errors_then_succeeds(client):
    route = respx.get(url__startswith=f"{BASE}/internal/v1/verifications/").mock(
        side_effect=[httpx.ConnectError("down"), httpx.Response(200, json={"data": {}})]
    )
    assert await client.get_verification(uuid4()) == {}
    assert route.call_count == 2


@respx.mock
async def test_get_gives_up_after_bounded_attempts(client):
    route = respx.get(url__startswith=f"{BASE}/internal/v1/verifications/").mock(
        side_effect=httpx.ConnectTimeout("slow")
    )
    with pytest.raises(UpstreamError):
        await client.get_verification(uuid4())
    assert route.call_count == 3


@respx.mock
async def test_post_is_not_retried(client):
    route = respx.post(f"{BASE}/internal/v1/audit-events").mock(
        side_effect=httpx.ConnectError("down")
    )
    with pytest.raises(UpstreamError):
        await client.post_audit_event("ai.test")
    assert route.call_count == 1


@respx.mock
async def test_audit_event_payload(client):
    eid = uuid4()
    route = respx.post(f"{BASE}/internal/v1/audit-events").respond(json={"data": {}})
    await client.post_audit_event(
        "ai.analysis_completed", entity_type="verification", entity_id=eid, metadata={"n": 1}
    )
    body = route.calls.last.request.read()
    assert str(eid).encode() in body
    assert b'"action":"ai.analysis_completed"' in body.replace(b" ", b"")


def test_timeouts_configured():
    core = CoreApiClient(BASE)
    timeout = core._client.timeout
    assert timeout.connect == 3.0
    assert timeout.read == 15.0
