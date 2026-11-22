"""Agency normalisation and SLBFE payload parsing."""

from __future__ import annotations

from datetime import date

import pytest

from app.integrations.slbfe.parser import (
    normalize_status,
    parse_csv,
    parse_json,
    parse_payload,
)
from app.models.enums import AgencyLicenseStatus
from app.utils.text import normalize_license_no, normalize_name, normalize_phone


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Lanka  Safe & Employment Agency", "lanka safe and employment agency"),
        ("  GLOBAL   DREAMS  ", "global dreams"),
        ("Star-Overseas (Pvt) Ltd.", "star overseas pvt ltd"),
    ],
)
def test_normalize_name(raw: str, expected: str) -> None:
    assert normalize_name(raw) == expected


def test_normalize_phone_and_license() -> None:
    assert normalize_phone("0094 77 123 4567") == "+94771234567"
    assert normalize_license_no("lic 12 34") == "LIC1234"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Active", AgencyLicenseStatus.ACTIVE),
        ("SUSPENDED", AgencyLicenseStatus.SUSPENDED),
        ("Expired", AgencyLicenseStatus.EXPIRED),
        ("revoked", AgencyLicenseStatus.CANCELLED),
        ("license mismatch", AgencyLicenseStatus.UNKNOWN),
        (None, AgencyLicenseStatus.UNKNOWN),
    ],
)
def test_normalize_status(raw, expected: AgencyLicenseStatus) -> None:
    assert normalize_status(raw) == expected


CSV = """registration_no,name,license_no,license_status,license_expires_on,district,job_categories
SLBFE/1,Lanka Safe Agency,LIC-1,Active,2027-03-31,Colombo,domestic|hospitality
SLBFE/2,Global Dreams,LIC-2,Suspended,31/12/2026,Gampaha,
bad-row,,,,,,
"""


def test_parse_csv() -> None:
    parsed = parse_csv(CSV.encode("utf-8"))
    assert len(parsed.records) == 2
    assert parsed.errors
    first = parsed.records[0]
    assert first.license_status == AgencyLicenseStatus.ACTIVE
    assert first.license_expires_on == date(2027, 3, 31)
    assert first.job_categories == ["domestic", "hospitality"]
    second = parsed.records[1]
    assert second.license_status == AgencyLicenseStatus.SUSPENDED
    assert second.license_expires_on == date(2026, 12, 31)


def test_parse_json_wrapped() -> None:
    payload = (
        '{"agencies": [{"registration_no": "SLBFE/3", "name": "Sunrise", '
        '"license_status": "expired", "expires_on": "2025-01-02"}]}'
    )
    parsed = parse_json(payload.encode("utf-8"))
    assert parsed.records[0].license_status == AgencyLicenseStatus.EXPIRED
    assert parsed.records[0].license_expires_on == date(2025, 1, 2)


def test_parse_payload_detects_json() -> None:
    assert parse_payload(b'[{"registration_no":"X","name":"Y"}]').records


def test_parse_json_rejects_non_list() -> None:
    with pytest.raises(ValueError):
        parse_json(b'{"agencies": "nope"}')
