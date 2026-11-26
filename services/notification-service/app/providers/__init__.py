"""Provider factory wired from settings."""

from __future__ import annotations

from app.core.config import settings
from app.providers.base import PushProvider, WhatsAppProviderProtocol
from app.providers.fcm import FcmPushProvider
from app.providers.stub import StubPushProvider
from app.providers.whatsapp import WhatsAppProvider


def build_push_provider() -> PushProvider:
    if settings.PUSH_PROVIDER == "fcm":
        return FcmPushProvider(
            project_id=settings.FCM_PROJECT_ID,
            service_account_file=settings.FCM_SERVICE_ACCOUNT_FILE,
            service_account_json=settings.FCM_SERVICE_ACCOUNT_JSON.get_secret_value(),
            api_url=settings.FCM_API_URL,
            timeout=settings.FCM_TIMEOUT_SECONDS,
        )
    return StubPushProvider(settings.STUB_FAILURE_MODE)


def build_whatsapp_provider() -> WhatsAppProviderProtocol | None:
    if not settings.WHATSAPP_ENABLED:
        return None
    return WhatsAppProvider(
        api_url=settings.WHATSAPP_API_URL,
        phone_number_id=settings.WHATSAPP_PHONE_NUMBER_ID,
        access_token=settings.WHATSAPP_ACCESS_TOKEN.get_secret_value(),
        template_name=settings.WHATSAPP_TEMPLATE_NAME,
        template_language=settings.WHATSAPP_TEMPLATE_LANGUAGE,
        timeout=settings.WHATSAPP_TIMEOUT_SECONDS,
    )
