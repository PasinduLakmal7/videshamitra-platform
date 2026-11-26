from __future__ import annotations

from datetime import date
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.guardrails.sources import (
    DocumentCitation,
    Finding,
    GroundingContext,
    RuleCitation,
    SlbfeCitation,
    ground,
)

DOC = uuid4()
UNPAGED = uuid4()
CTX = GroundingContext(
    document_pages={DOC: 2, UNPAGED: None},
    rule_ids=frozenset({"fee_above_cap"}),
    slbfe_record_ids=frozenset({"slbfe-123"}),
)


def finding(citation=None, code="fee_above_cap") -> Finding:
    return Finding(code=code, message="m", severity="high", citation=citation)


@pytest.mark.parametrize(
    "citation",
    [
        DocumentCitation(document_id=DOC, page=2, quote="Fee: LKR 500,000"),
        DocumentCitation(document_id=UNPAGED, page=7),
        SlbfeCitation(record_id="slbfe-123", list_date=date(2026, 11, 1)),
        RuleCitation(rule_id="fee_above_cap"),
    ],
)
def test_cited_findings_are_kept(citation):
    result = ground([finding(citation)], CTX)
    assert result.findings == [finding(citation)]
    assert result.dropped == {}
    assert not result.unable_to_verify


@pytest.mark.parametrize(
    ("citation", "reason"),
    [
        (None, "uncited"),
        (DocumentCitation(document_id=uuid4(), page=1), "unknown_document"),
        (DocumentCitation(document_id=DOC, page=3), "page_out_of_range"),
        (SlbfeCitation(record_id="made-up", list_date=date(2026, 11, 1)), "unknown_slbfe_record"),
        (RuleCitation(rule_id="admin_override"), "unknown_rule"),
    ],
)
def test_ungrounded_findings_are_dropped(citation, reason):
    result = ground([finding(citation)], CTX)
    assert result.findings == []
    assert result.dropped == {reason: 1}


def test_no_grounded_findings_means_unable_to_verify():
    assert ground([], CTX).unable_to_verify
    mixed = ground([finding(None), finding(RuleCitation(rule_id="fee_above_cap"))], CTX)
    assert len(mixed.findings) == 1
    assert mixed.dropped == {"uncited": 1}
    assert not mixed.unable_to_verify


def test_citation_shape_is_strict():
    with pytest.raises(ValidationError):
        Finding.model_validate(
            {"code": "x", "message": "m", "citation": {"kind": "rule", "rule_id": "r", "x": 1}}
        )
    with pytest.raises(ValidationError):
        Finding.model_validate(
            {"code": "x", "message": "m", "citation": {"kind": "document", "page": 1}}
        )
    with pytest.raises(ValidationError):
        Finding.model_validate({"code": "x", "message": "m", "status": "verified"})
    parsed = Finding.model_validate(
        {
            "code": "x",
            "message": "m",
            "citation": {"kind": "slbfe_record", "record_id": "r", "list_date": "2026-11-01"},
        }
    )
    assert isinstance(parsed.citation, SlbfeCitation)
