"""WhatsApp webhook verification and forwarding to ai-service."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
from uuid import NAMESPACE_URL, uuid5

import asyncpg
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, PlainTextResponse

from app.api.dependencies import get_ai_client
from app.core.config import settings
from app.core.exceptions import Forbidden, ServiceUnavailable
from app.db.pool import get_connection
from app.events.publisher import mark_processed

logger = logging.getLogger(__name__)

router = APIRouter()
CONSUMER = "whatsapp-webhook"


def _verify_signature(raw: bytes, signature: str | None) -> None:
    if not settings.WHATSAPP_APP_SECRET:
        if settings.is_production:
            raise ServiceUnavailable(
                "WhatsApp webhook secret is not configured",
                code="webhook_not_configured",
            )
        logger.warning("whatsapp_signature_check_disabled")
        return
    if not signature or not signature.startswith("sha256="):
        raise Forbidden("Missing webhook signature", code="invalid_signature")
    expected = hmac.new(
        settings.WHATSAPP_APP_SECRET.encode("utf-8"), raw, hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(expected, signature.split("=", 1)[1]):
        raise Forbidden("Invalid webhook signature", code="invalid_signature")


def _message_ids(payload: dict) -> list[str]:
    ids: list[str] = []
    for entry in payload.get("entry", []) or []:
        for change in entry.get("changes", []) or []:
            value = change.get("value", {}) or {}
            for message in value.get("messages", []) or []:
                if message.get("id"):
                    ids.append(str(message["id"]))
    return ids


@router.get("/whatsapp", response_class=PlainTextResponse)
async def verify_whatsapp(
    request: Request,
):
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge", "")
    if (
        mode == "subscribe"
        and settings.WHATSAPP_VERIFY_TOKEN
        and token == settings.WHATSAPP_VERIFY_TOKEN
    ):
        return PlainTextResponse(challenge)
    raise Forbidden("Webhook verification failed", code="webhook_verification_failed")


@router.post("/whatsapp")
async def whatsapp_webhook(
    request: Request,
    conn: asyncpg.Connection = Depends(get_connection),
    client=Depends(get_ai_client),
):
    raw = await request.body()
    _verify_signature(raw, request.headers.get("X-Hub-Signature-256"))
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        from app.core.exceptions import BadRequest

        raise BadRequest("Invalid JSON payload", code="invalid_json") from exc

    message_ids = _message_ids(payload)
    new_ids: list[str] = []
    for message_id in message_ids:
        event_uuid = uuid5(NAMESPACE_URL, f"whatsapp:{message_id}")
        exists = await conn.fetchval(
            "select 1 from core.event_dedupe where consumer = $1 and event_id = $2",
            CONSUMER,
            event_uuid,
        )
        if exists is None:
            new_ids.append(message_id)

    if not message_ids or new_ids:
        await client.forward_whatsapp(payload, new_ids[0] if new_ids else None)
        for message_id in new_ids:
            await mark_processed(conn, CONSUMER, uuid5(NAMESPACE_URL, f"whatsapp:{message_id}"))

    return JSONResponse({"status": "ok"})
