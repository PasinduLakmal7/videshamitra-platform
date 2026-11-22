"""Normalise SLBFE agency records from CSV or JSON."""

from __future__ import annotations

import csv
import io
import json
import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from app.models.enums import AgencyLicenseStatus
from app.utils.text import normalize_license_no, normalize_name, normalize_phone

logger = logging.getLogger(__name__)

_DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d", "%d.%m.%Y")

_STATUS_MAP = {
    "active": AgencyLicenseStatus.ACTIVE,
    "valid": AgencyLicenseStatus.ACTIVE,
    "suspended": AgencyLicenseStatus.SUSPENDED,
    "suspend": AgencyLicenseStatus.SUSPENDED,
    "expired": AgencyLicenseStatus.EXPIRED,
    "expire": AgencyLicenseStatus.EXPIRED,
    "cancelled": AgencyLicenseStatus.CANCELLED,
    "canceled": AgencyLicenseStatus.CANCELLED,
    "revoked": AgencyLicenseStatus.CANCELLED,
    "unknown": AgencyLicenseStatus.UNKNOWN,
    "mismatch": AgencyLicenseStatus.UNKNOWN,
    "license mismatch": AgencyLicenseStatus.UNKNOWN,
}


@dataclass
class AgencyRecord:
    registration_no: str
    name: str
    normalized_name: str
    license_no: str | None = None
    license_status: AgencyLicenseStatus = AgencyLicenseStatus.UNKNOWN
    license_expires_on: date | None = None
    issued_on: date | None = None
    address: str | None = None
    district: str | None = None
    phone: str | None = None
    email: str | None = None
    job_categories: list[str] = field(default_factory=list)
    raw_data: dict[str, Any] = field(default_factory=dict)


@dataclass
class ParseResult:
    records: list[AgencyRecord]
    errors: list[str]

    @property
    def record_count(self) -> int:
        return len(self.records)


def parse_date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, date):
        return value
    text = str(value).strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text[:10], fmt).date()
        except ValueError:
            continue
    logger.warning("slbfe_unparseable_date", extra={"value": text[:40]})
    return None


def normalize_status(value: Any) -> AgencyLicenseStatus:
    text = normalize_name(str(value or ""))
    return _STATUS_MAP.get(text, AgencyLicenseStatus.UNKNOWN)


def _split_categories(value: Any) -> list[str]:
    if value in (None, ""):
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [part.strip() for part in str(value).split("|") if part.strip()]


def _record_from_mapping(row: dict[str, Any]) -> AgencyRecord | None:
    registration = str(row.get("registration_no") or row.get("registration_number") or "").strip()
    name = str(row.get("name") or row.get("agency_name") or "").strip()
    if not registration or not name:
        return None
    return AgencyRecord(
        registration_no=registration,
        name=name,
        normalized_name=normalize_name(name),
        license_no=normalize_license_no(row.get("license_no") or row.get("license_number")),
        license_status=normalize_status(row.get("license_status") or row.get("status")),
        license_expires_on=parse_date(row.get("license_expires_on") or row.get("expires_on")),
        issued_on=parse_date(row.get("issued_on") or row.get("license_issued_on")),
        address=(str(row.get("address")).strip() if row.get("address") else None),
        district=(str(row.get("district")).strip() if row.get("district") else None),
        phone=normalize_phone(row.get("phone")),
        email=(str(row.get("email")).strip() if row.get("email") else None),
        job_categories=_split_categories(row.get("job_categories")),
        raw_data={str(key): value for key, value in row.items()},
    )


def parse_csv(raw: bytes) -> ParseResult:
    text = raw.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    records: list[AgencyRecord] = []
    errors: list[str] = []
    for line_number, row in enumerate(reader, start=2):
        record = _record_from_mapping(dict(row))
        if record is None:
            errors.append(f"line {line_number}: missing registration_no or name")
            continue
        records.append(record)
    return ParseResult(records, errors)


def parse_json(raw: bytes) -> ParseResult:
    payload = json.loads(raw.decode("utf-8-sig"))
    if isinstance(payload, dict):
        rows = payload.get("agencies") or payload.get("records") or payload.get("data") or []
    else:
        rows = payload
    if not isinstance(rows, list):
        raise ValueError("JSON payload must contain a list of agency records")
    records: list[AgencyRecord] = []
    errors: list[str] = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            errors.append(f"row {index}: expected an object")
            continue
        record = _record_from_mapping(row)
        if record is None:
            errors.append(f"row {index}: missing registration_no or name")
            continue
        records.append(record)
    return ParseResult(records, errors)


def parse_payload(raw: bytes, content_type: str | None = None) -> ParseResult:
    content_type = (content_type or "").lower()
    stripped = raw.lstrip()
    if "json" in content_type or stripped.startswith((b"[", b"{")):
        return parse_json(raw)
    return parse_csv(raw)
