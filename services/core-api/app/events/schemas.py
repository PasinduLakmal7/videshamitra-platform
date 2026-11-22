"""Versioned event contracts for Redis Streams.

The Pydantic models here are the canonical producer/consumer contract.  The
JSON Schemas in `packages/contracts/schemas/` are generated from these models
(see `scripts/export_contracts.py`); never edit generated schemas by hand.
"""

from __future__ import annotations

import socket
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID, uuid4, uuid5

from pydantic import BaseModel, ConfigDict, Field, field_validator

PRODUCER = "core-api"
_NAMESPACE = UUID("7d7a2c73-6f39-4f9b-9a1d-5b1a1f9c2d10")


def _as_uuid(value: str | UUID | None) -> UUID:
    if isinstance(value, UUID):
        return value
    if value:
        try:
            return UUID(str(value))
        except ValueError:
            return uuid5(_NAMESPACE, str(value))
    return uuid4()


def utcnow() -> datetime:
    return datetime.now(UTC)


class EventEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: UUID
    event_type: str
    version: int = 1
    occurred_at: datetime
    producer: str
    trace_id: UUID
    data: dict[str, Any]

    @field_validator("occurred_at")
    @classmethod
    def _utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


class AgencyRef(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: UUID | None = None
    registration_no: str | None = None
    name: str | None = None
    license_no: str | None = None
    license_status: str = "unknown"
    license_expires_on: str | None = None


class JobDetails(BaseModel):
    model_config = ConfigDict(extra="ignore")

    title: str | None = None
    employer_name: str | None = None
    destination_country: str | None = None
    offered_salary: float | None = None
    currency: str | None = None


class DocumentRef(BaseModel):
    model_config = ConfigDict(extra="ignore")

    document_id: UUID
    type: str
    mime_type: str
    page_count: int | None = None


class VerificationRequestedData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    verification_id: UUID
    user_id: UUID
    locale: str = "en"
    agency: AgencyRef | None = None
    job: JobDetails
    documents: list[DocumentRef] = Field(default_factory=list)


class Finding(BaseModel):
    model_config = ConfigDict(extra="allow")

    code: str
    message: str
    source: str | None = None


class EvidenceRef(BaseModel):
    model_config = ConfigDict(extra="allow")

    document_id: UUID | None = None
    page: int | None = None
    quote: str | None = None


class VerificationCompletedData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    verification_id: UUID
    status: Literal["verified", "suspicious", "fraudulent"]
    risk_level: Literal["low", "medium", "high", "critical"]
    risk_score: int | None = Field(default=None, ge=0, le=100)
    findings: list[Finding] = Field(default_factory=list)
    evidence: list[EvidenceRef] = Field(default_factory=list)
    engine_version: str | None = None
    analysis_run_id: str | None = None


class VerificationFailedData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    verification_id: UUID
    error_code: str
    message: str
    retryable: bool = False


class NotificationRequestedData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    notification_id: UUID
    user_id: UUID
    locale: str = "en"
    type: str
    title: str
    body: str
    data: dict[str, Any] = Field(default_factory=dict)
    deep_link: str | None = None
    channels: list[str] = Field(default_factory=lambda: ["in_app"])


class VerificationRequestedEvent(EventEnvelope):
    event_type: Literal["verification.requested"] = "verification.requested"
    data: VerificationRequestedData  # type: ignore[assignment]


class VerificationCompletedEvent(EventEnvelope):
    event_type: Literal["verification.completed"] = "verification.completed"
    data: VerificationCompletedData  # type: ignore[assignment]


class VerificationFailedEvent(EventEnvelope):
    event_type: Literal["verification.failed"] = "verification.failed"
    data: VerificationFailedData  # type: ignore[assignment]


class NotificationRequestedEvent(EventEnvelope):
    event_type: Literal["notification.requested"] = "notification.requested"
    data: NotificationRequestedData  # type: ignore[assignment]


EVENT_MODELS: dict[str, type[EventEnvelope]] = {
    "verification.requested": VerificationRequestedEvent,
    "verification.completed": VerificationCompletedEvent,
    "verification.failed": VerificationFailedEvent,
    "notification.requested": NotificationRequestedEvent,
}


def make_event(
    event_type: str,
    data: dict[str, Any] | BaseModel,
    *,
    producer: str = PRODUCER,
    trace_id: str | UUID | None = None,
    event_id: UUID | None = None,
    version: int = 1,
) -> EventEnvelope:
    model = EVENT_MODELS.get(event_type)
    payload = data.model_dump(mode="json") if isinstance(data, BaseModel) else data
    if model is not None:
        return model(
            event_id=event_id or uuid4(),
            event_type=event_type,
            version=version,
            occurred_at=utcnow(),
            producer=producer,
            trace_id=_as_uuid(trace_id),
            data=payload,
        )
    return EventEnvelope(
        event_id=event_id or uuid4(),
        event_type=event_type,
        version=version,
        occurred_at=utcnow(),
        producer=producer,
        trace_id=_as_uuid(trace_id),
        data=payload,
    )


def parse_event(raw: dict[str, Any]) -> EventEnvelope:
    event_type = raw.get("event_type")
    model = EVENT_MODELS.get(event_type)
    if model is None:
        return EventEnvelope.model_validate(raw)
    return model.model_validate(raw)


def consumer_name() -> str:
    return f"{socket.gethostname()}-{uuid4().hex[:8]}"
