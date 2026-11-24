"""JSON logs with correlation ids; every record is PII-redacted before it is emitted."""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any

from app.core.config import settings
from app.core.request_id import request_id_var, trace_id_var
from app.guardrails.pii import redact

_RESERVED = set(logging.LogRecord("", 0, "", 0, "", None, None).__dict__) | {"message", "asctime"}


class PiiRedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact(str(record.msg))
        if record.args:
            args = record.args if isinstance(record.args, tuple) else (record.args,)
            record.args = tuple(redact(a) if isinstance(a, str) else a for a in args)
        for key, value in list(record.__dict__.items()):
            if key not in _RESERVED and isinstance(value, str):
                setattr(record, key, redact(value))
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "service": settings.SERVICE_NAME,
            "message": record.getMessage(),
            "request_id": request_id_var.get() or None,
            "trace_id": trace_id_var.get() or None,
        }
        for key, value in record.__dict__.items():
            if key in _RESERVED or key.startswith("_"):
                continue
            if isinstance(value, (str, int, float, bool, list, dict)) or value is None:
                payload[key] = value
        if record.exc_info:
            payload["exception"] = redact(self.formatException(record.exc_info))
        return json.dumps(payload, default=str, ensure_ascii=False)


def build_handler() -> logging.Handler:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    handler.addFilter(PiiRedactingFilter())
    return handler


def setup_logging() -> None:
    level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(build_handler())
    root.setLevel(level)
    for noisy in ("uvicorn.access", "httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(max(level, logging.WARNING))
