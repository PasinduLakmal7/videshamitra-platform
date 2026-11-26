"""Request/trace ids in contextvars, set by a pure ASGI middleware."""

from __future__ import annotations

import contextvars
import logging
import time
import uuid

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="")
trace_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("trace_id", default="")

logger = logging.getLogger("app.access")


def current_request_id() -> str:
    return request_id_var.get() or str(uuid.uuid4())


def current_trace_id() -> str:
    return trace_id_var.get() or current_request_id()


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        request_id = headers.get("x-request-id", "").strip()[:128] or str(uuid.uuid4())
        trace_id = headers.get("x-trace-id", "").strip()[:128] or request_id
        rid_token = request_id_var.set(request_id)
        trace_token = trace_id_var.set(trace_id)
        started = time.perf_counter()
        status_code = 500

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                response_headers = MutableHeaders(scope=message)
                response_headers["X-Request-ID"] = request_id
                response_headers["X-Trace-ID"] = trace_id
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            logger.info(
                "http_request",
                extra={
                    "http_method": scope["method"],
                    "http_route": scope["path"],
                    "http_status": status_code,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                },
            )
            request_id_var.reset(rid_token)
            trace_id_var.reset(trace_token)
