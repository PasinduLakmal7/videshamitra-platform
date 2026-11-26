from __future__ import annotations

import json

import httpx
import pytest
import respx

from app.providers.base import PushMessage, WhatsAppMessage
from app.providers.fcm import FcmPushProvider
from app.providers.whatsapp import WhatsAppProvider


def _push() -> PushMessage:
    return PushMessage(
        token="fcm-token",
        title="Safety check-in",
        body="How are you?",
        data={"type": "checkin_due", "deep_link": "videshamitra://checkins/1"},
        notification_id="n-1",
    )


@pytest.fixture
async def fcm_provider():
    client = httpx.AsyncClient()
    provider = FcmPushProvider(
        project_id="test-project",
        api_url="https://fcm.test",
        client=client,
    )

    async def token() -> str:
        return "access-token"

    provider._access_token = token
    yield provider
    await provider.aclose()


async def test_fcm_success(fcm_provider):
    with respx.mock:
        route = respx.post("https://fcm.test/v1/projects/test-project/messages:send").mock(
            return_value=httpx.Response(200, json={"name": "projects/test/messages/1"})
        )
        result = await fcm_provider.send(_push())
    assert result.success
    assert result.provider_message_id == "projects/test/messages/1"
    request = route.calls[0].request
    body = json.loads(request.content)
    assert body["message"]["token"] == "fcm-token"
    assert body["message"]["data"]["type"] == "checkin_due"
    assert request.headers["authorization"] == "Bearer access-token"


async def test_fcm_unregistered_prunes_token(fcm_provider):
    with respx.mock:
        respx.post("https://fcm.test/v1/projects/test-project/messages:send").mock(
            return_value=httpx.Response(
                404,
                json={
                    "error": {
                        "status": "UNREGISTERED",
                        "message": "Requested entity was not found.",
                    }
                },
            )
        )
        result = await fcm_provider.send(_push())
    assert not result.success
    assert result.invalid_token
    assert result.error_code == "device_unregistered"


async def test_fcm_retryable_status(fcm_provider):
    with respx.mock:
        respx.post("https://fcm.test/v1/projects/test-project/messages:send").mock(
            return_value=httpx.Response(
                503,
                headers={"Retry-After": "120"},
                json={"error": {"status": "UNAVAILABLE", "message": "try later"}},
            )
        )
        result = await fcm_provider.send(_push())
    assert result.retryable
    assert result.retry_after_seconds == 120


async def test_fcm_auth_error_is_permanent(fcm_provider):
    with respx.mock:
        respx.post("https://fcm.test/v1/projects/test-project/messages:send").mock(
            return_value=httpx.Response(
                403,
                json={"error": {"status": "PERMISSION_DENIED", "message": "denied"}},
            )
        )
        result = await fcm_provider.send(_push())
    assert not result.success
    assert not result.retryable
    assert result.error_code == "provider_auth_error"


@pytest.fixture
async def whatsapp_provider():
    client = httpx.AsyncClient()
    provider = WhatsAppProvider(
        api_url="https://wa.test/v21.0",
        phone_number_id="phone-1",
        access_token="wa-token",
        template_name="notification_generic",
        template_language="en",
        client=client,
    )
    yield provider
    await provider.aclose()


def _wa() -> WhatsAppMessage:
    return WhatsAppMessage(
        recipient="+94770000000",
        title="Safety check-in",
        body="How are you?",
        locale="en",
        notification_id="n-1",
    )


async def test_whatsapp_success(whatsapp_provider):
    with respx.mock:
        route = respx.post("https://wa.test/v21.0/phone-1/messages").mock(
            return_value=httpx.Response(200, json={"messages": [{"id": "wamid.1"}]})
        )
        result = await whatsapp_provider.send(_wa())
    assert result.success
    assert result.provider_message_id == "wamid.1"
    body = json.loads(route.calls[0].request.content)
    assert body["to"] == "+94770000000"
    assert body["template"]["name"] == "notification_generic"


async def test_whatsapp_429_is_retryable(whatsapp_provider):
    with respx.mock:
        respx.post("https://wa.test/v21.0/phone-1/messages").mock(
            return_value=httpx.Response(
                429,
                headers={"Retry-After": "60"},
                json={"error": {"code": 429, "message": "rate limited"}},
            )
        )
        result = await whatsapp_provider.send(_wa())
    assert result.retryable
    assert result.retry_after_seconds == 60
