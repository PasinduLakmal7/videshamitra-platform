from __future__ import annotations

import io
import json
import logging

import pytest

from app.core.logging import JsonFormatter, PiiRedactingFilter
from app.core.request_id import request_id_var, trace_id_var
from app.guardrails.pii import redact


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("mail worker@example.com now", "mail [EMAIL] now"),
        ("nic 199012345678 ok", "nic [NIC] ok"),
        ("nic 901234567V ok", "nic [NIC] ok"),
        ("call +94 77 123 4567", "call [PHONE]"),
        ("call 077-123-4567.", "call [PHONE]."),
    ],
)
def test_redact_masks_pii(text, expected):
    assert redact(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "verification 3f2b8c1e-1234-5678-9abc-123456789012",
        "id 12345678-1234-1234-1234-123456789012",
        "on 2026-11-24 at 10:15",
        "took 1500 ms, page 3",
    ],
)
def test_redact_leaves_ids_and_dates(text):
    assert redact(text) == text


def _capture() -> tuple[logging.Logger, io.StringIO]:
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    handler.addFilter(PiiRedactingFilter())
    logger = logging.getLogger("test.pii")
    logger.handlers = [handler]
    logger.propagate = False
    logger.setLevel(logging.INFO)
    return logger, stream


def test_log_line_is_redacted_json_with_ids():
    logger, stream = _capture()
    rid = request_id_var.set("req-9")
    tid = trace_id_var.set("trace-9")
    try:
        logger.info("user %s phoned %s", "a@b.com", "0771234567", extra={"note": "nic 901234567V"})
    finally:
        request_id_var.reset(rid)
        trace_id_var.reset(tid)
    line = json.loads(stream.getvalue())
    assert line["message"] == "user [EMAIL] phoned [PHONE]"
    assert line["note"] == "nic [NIC]"
    assert line["service"] == "ai-service"
    assert line["request_id"] == "req-9"
    assert line["trace_id"] == "trace-9"
