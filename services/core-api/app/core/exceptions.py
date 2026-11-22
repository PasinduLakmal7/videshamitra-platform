"""Application error types and the public error codes."""

from __future__ import annotations

from typing import Any


class AppError(Exception):
    status_code: int = 500
    code: str = "internal_error"

    def __init__(
        self,
        message: str | None = None,
        *,
        status_code: int | None = None,
        code: str | None = None,
        details: Any = None,
    ) -> None:
        self.message = message or self.code.replace("_", " ").capitalize()
        if status_code is not None:
            self.status_code = status_code
        if code is not None:
            self.code = code
        self.details = details
        super().__init__(self.message)


class BadRequest(AppError):
    status_code = 400
    code = "bad_request"


class Unauthorized(AppError):
    status_code = 401
    code = "unauthorized"


class Forbidden(AppError):
    status_code = 403
    code = "forbidden"


class NotFound(AppError):
    status_code = 404
    code = "not_found"


class Conflict(AppError):
    status_code = 409
    code = "conflict"


class Gone(AppError):
    status_code = 410
    code = "gone"


class UnprocessableEntity(AppError):
    status_code = 422
    code = "unprocessable_entity"


class PayloadTooLarge(AppError):
    status_code = 413
    code = "payload_too_large"


class RateLimited(AppError):
    status_code = 429
    code = "rate_limited"


class ServiceUnavailable(AppError):
    status_code = 503
    code = "service_unavailable"


class UpstreamError(AppError):
    status_code = 502
    code = "upstream_error"

    def __init__(
        self,
        message: str = "Upstream service failed",
        *,
        service: str | None = None,
        details: Any = None,
    ) -> None:
        super().__init__(message, details=details)
        if service:
            self.details = {"service": service, **({"detail": details} if details else {})}
