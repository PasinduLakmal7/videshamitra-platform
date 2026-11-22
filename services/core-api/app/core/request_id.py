"""Request/trace correlation identifiers.

`X-Request-ID` is accepted from the caller (Kong or an internal service) and is
always echoed on the response.  The same identifier is used as the event
`trace_id` so one request can be followed across core -> AI -> core.
"""

from __future__ import annotations

import contextvars
import time
import uuid
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="")
trace_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("trace_id", default="")
user_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("user_id", default="")


def current_request_id() -> str:
    return request_id_var.get() or str(uuid.uuid4())


def current_trace_id() -> str:
    return trace_id_var.get() or current_request_id()


def bind_trace_id(trace_id: str | None) -> None:
    if trace_id:
        trace_id_var.set(trace_id)


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Attach request/trace ids and emit one structured access log line."""

    def __init__(self, app, logger) -> None:  # type: ignore[no-untyped-def]
        super().__init__(app)
        self._logger = logger

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        incoming = request.headers.get("X-Request-ID", "").strip()
        request_id = incoming[:128] if incoming else str(uuid.uuid4())
        trace_id = request.headers.get("X-Trace-ID", "").strip() or request_id
        rid_token = request_id_var.set(request_id)
        trace_token = trace_id_var.set(trace_id[:128])
        user_token = user_id_var.set("")
        started = time.perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers["X-Request-ID"] = request_id
            response.headers["X-Trace-ID"] = trace_id
            return response
        finally:
            authenticated = getattr(request.state, "user", None)
            duration_ms = round((time.perf_counter() - started) * 1000, 2)
            self._logger.info(
                "http_request",
                extra={
                    "http_method": request.method,
                    "http_route": request.url.path,
                    "http_status": status_code,
                    "duration_ms": duration_ms,
                    "user_id": str(authenticated.id) if authenticated else None,
                    "client_ip": request.client.host if request.client else None,
                },
            )
            request_id_var.reset(rid_token)
            trace_id_var.reset(trace_token)
            user_id_var.reset(user_token)
