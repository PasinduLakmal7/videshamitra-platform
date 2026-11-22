"""State machines, risk inference and pagination helpers."""

from __future__ import annotations

import pytest

from app.core.exceptions import BadRequest
from app.models.enums import (
    COMPLAINT_TRANSITIONS,
    VERIFICATION_TRANSITIONS,
    ComplaintStatus,
    VerificationStatus,
    can_transition,
)
from app.schemas.common import PageParams
from app.services.migration_service import infer_risk


@pytest.mark.parametrize(
    ("current", "target", "allowed"),
    [
        (VerificationStatus.PENDING, VerificationStatus.PROCESSING, True),
        (VerificationStatus.PROCESSING, VerificationStatus.VERIFIED, True),
        (VerificationStatus.PROCESSING, VerificationStatus.FRAUDULENT, True),
        (VerificationStatus.VERIFIED, VerificationStatus.PENDING, False),
        (VerificationStatus.FRAUDULENT, VerificationStatus.PROCESSING, False),
        (VerificationStatus.FAILED, VerificationStatus.PENDING, True),
        (VerificationStatus.PENDING, VerificationStatus.PENDING, True),
    ],
)
def test_verification_transitions(current, target, allowed) -> None:
    assert can_transition(VERIFICATION_TRANSITIONS, current, target) is allowed


@pytest.mark.parametrize(
    ("current", "target", "allowed"),
    [
        (ComplaintStatus.DRAFT, ComplaintStatus.SUBMITTED, True),
        (ComplaintStatus.DRAFT, ComplaintStatus.RESOLVED, False),
        (ComplaintStatus.SUBMITTED, ComplaintStatus.UNDER_REVIEW, True),
        (ComplaintStatus.UNDER_REVIEW, ComplaintStatus.ESCALATED, True),
        (ComplaintStatus.ESCALATED, ComplaintStatus.RESOLVED, True),
        (ComplaintStatus.RESOLVED, ComplaintStatus.CLOSED, True),
        (ComplaintStatus.CLOSED, ComplaintStatus.SUBMITTED, False),
    ],
)
def test_complaint_transitions(current, target, allowed) -> None:
    assert can_transition(COMPLAINT_TRANSITIONS, current, target) is allowed


@pytest.mark.parametrize(
    ("response", "expected"),
    [
        ({"risk_level": "critical"}, "critical"),
        ({"is_safe": False}, "high"),
        ({"note": "passport confiscated by employer"}, "high"),
        ({"is_safe": True}, None),
        ({}, None),
    ],
)
def test_infer_risk(response, expected) -> None:
    risk = infer_risk(response)
    assert (risk.value if risk else None) == expected


def test_pagination_offsets_and_sort() -> None:
    params = PageParams(page=3, page_size=25)
    assert params.offset == 50
    assert params.resolve_sort({"created_at": "created_at"}, "created_at") == "created_at DESC"


def test_pagination_invalid_sort() -> None:
    params = PageParams(page=1, page_size=20, sort="drop table")
    with pytest.raises(BadRequest) as exc:
        params.resolve_sort({"created_at": "created_at"}, "created_at")
    assert exc.value.code == "invalid_sort"


def test_page_size_bounds() -> None:
    with pytest.raises(BadRequest):
        PageParams(page=1, page_size=101)
    with pytest.raises(BadRequest):
        PageParams(page=0, page_size=20)
