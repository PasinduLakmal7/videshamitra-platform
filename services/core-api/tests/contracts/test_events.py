"""Event envelope and contract payloads."""

from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.events.envelope import decode_from_stream, encode_for_stream
from app.events.schemas import (
    NotificationRequestedEvent,
    VerificationCompletedEvent,
    VerificationFailedEvent,
    VerificationRequestedEvent,
    make_event,
    parse_event,
)


def _envelope(event_type: str, data: dict) -> dict:
    return make_event(event_type, data).model_dump(mode="json")


def test_verification_requested_contract() -> None:
    event = _envelope(
        "verification.requested",
        {
            "verification_id": str(uuid4()),
            "user_id": str(uuid4()),
            "locale": "si",
            "agency": {
                "id": str(uuid4()),
                "registration_no": "SLBFE/1234",
                "name": "Example Agency",
                "license_no": "LIC-5678",
                "license_status": "active",
                "license_expires_on": "2027-03-31",
            },
            "job": {
                "title": "Domestic Worker",
                "employer_name": "Example Employer",
                "destination_country": "SA",
                "offered_salary": 45000,
                "currency": "LKR",
            },
            "documents": [
                {
                    "document_id": str(uuid4()),
                    "type": "job_offer",
                    "mime_type": "application/pdf",
                    "page_count": 2,
                }
            ],
        },
    )
    parsed = VerificationRequestedEvent.model_validate(event)
    assert parsed.event_type == "verification.requested"
    assert parsed.version == 1
    assert parsed.data.documents[0].type == "job_offer"


def test_verification_completed_contract() -> None:
    event = _envelope(
        "verification.completed",
        {
            "verification_id": str(uuid4()),
            "status": "suspicious",
            "risk_level": "high",
            "risk_score": 82,
            "findings": [
                {
                    "code": "salary_deduction",
                    "message": "Deduction exceeds 20%",
                    "source": "contract.pdf#p2",
                }
            ],
            "evidence": [{"page": 2, "quote": "..."}],
            "engine_version": "ai-service@1.0.0",
            "analysis_run_id": "b2c3",
        },
    )
    parsed = VerificationCompletedEvent.model_validate(event)
    assert parsed.data.status == "suspicious"


def test_invalid_risk_score_rejected() -> None:
    with pytest.raises(ValidationError):
        _envelope(
            "verification.completed",
            {
                "verification_id": str(uuid4()),
                "status": "verified",
                "risk_level": "low",
                "risk_score": 101,
            },
        )


def test_verification_failed_contract() -> None:
    event = _envelope(
        "verification.failed",
        {
            "verification_id": str(uuid4()),
            "error_code": "document_unreadable",
            "message": "The uploaded PDF could not be parsed",
            "retryable": False,
        },
    )
    parsed = VerificationFailedEvent.model_validate(event)
    assert parsed.data.retryable is False


def test_notification_requested_contract() -> None:
    event = _envelope(
        "notification.requested",
        {
            "notification_id": str(uuid4()),
            "user_id": str(uuid4()),
            "locale": "si",
            "type": "verification_complete",
            "title": "Verification complete",
            "body": "Your job offer has a high-risk finding.",
            "data": {"verification_id": str(uuid4())},
            "deep_link": "videshamitra://verifications/1",
            "channels": ["push", "whatsapp"],
        },
    )
    parsed = NotificationRequestedEvent.model_validate(event)
    assert parsed.data.channels == ["push", "whatsapp"]


def test_event_stream_round_trip() -> None:
    event = make_event(
        "verification.failed",
        {
            "verification_id": str(uuid4()),
            "error_code": "boom",
            "message": "failed",
            "retryable": True,
        },
    )
    encoded = encode_for_stream(event)
    decoded = decode_from_stream(encoded)
    assert decoded["event_id"] == str(event.event_id)
    assert decoded["event_type"] == "verification.failed"


def test_unknown_event_type_still_has_envelope() -> None:
    event = make_event("custom.event", {"x": 1})
    parsed = parse_event(event.model_dump(mode="json"))
    assert parsed.event_type == "custom.event"
