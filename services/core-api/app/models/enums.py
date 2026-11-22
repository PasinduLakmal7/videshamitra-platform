"""Domain enums shared by repositories, services and schemas."""

from __future__ import annotations

from enum import StrEnum


class UserRole(StrEnum):
    WORKER = "worker"
    CASEWORKER = "caseworker"
    ADMIN = "admin"


class LanguageCode(StrEnum):
    EN = "en"
    SI = "si"
    TA = "ta"


class ConsentType(StrEnum):
    DATA_PROCESSING = "data_processing"
    CHECKINS = "checkins"
    WHATSAPP = "whatsapp"


class AgencyLicenseStatus(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    EXPIRED = "expired"
    CANCELLED = "cancelled"
    UNKNOWN = "unknown"


class VerificationStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    VERIFIED = "verified"
    SUSPICIOUS = "suspicious"
    FRAUDULENT = "fraudulent"
    FAILED = "failed"


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class DocumentType(StrEnum):
    JOB_OFFER = "job_offer"
    EMPLOYMENT_CONTRACT = "employment_contract"
    PASSPORT = "passport"
    VISA = "visa"
    PAYMENT_RECEIPT = "payment_receipt"
    SCREENSHOT = "screenshot"
    OTHER = "other"


class DocumentStatus(StrEnum):
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    PROCESSED = "processed"
    FAILED = "failed"


class JourneyStage(StrEnum):
    PRE_DEPARTURE = "pre_departure"
    EMPLOYED_ABROAD = "employed_abroad"
    RETURNED = "returned"


class CheckinStatus(StrEnum):
    SCHEDULED = "scheduled"
    SENT = "sent"
    COMPLETED = "completed"
    MISSED = "missed"
    ESCALATED = "escalated"


class ComplaintStatus(StrEnum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    UNDER_REVIEW = "under_review"
    ESCALATED = "escalated"
    RESOLVED = "resolved"
    CLOSED = "closed"


class NotificationType(StrEnum):
    CHECKIN_DUE = "checkin_due"
    CHECKIN_MISSED = "checkin_missed"
    AGENCY_LICENSE_CHANGED = "agency_license_changed"
    VERIFICATION_COMPLETE = "verification_complete"
    COMPLAINT_UPDATE = "complaint_update"
    CASEWORKER_MESSAGE = "caseworker_message"
    SYSTEM = "system"


class NotificationChannel(StrEnum):
    IN_APP = "in_app"
    PUSH = "push"
    WHATSAPP = "whatsapp"
    EMAIL = "email"
    SMS = "sms"


VERIFICATION_TRANSITIONS: dict[str, set[str]] = {
    VerificationStatus.PENDING: {
        VerificationStatus.PROCESSING,
        VerificationStatus.FAILED,
    },
    VerificationStatus.PROCESSING: {
        VerificationStatus.VERIFIED,
        VerificationStatus.SUSPICIOUS,
        VerificationStatus.FRAUDULENT,
        VerificationStatus.FAILED,
    },
    VerificationStatus.VERIFIED: set(),
    VerificationStatus.SUSPICIOUS: set(),
    VerificationStatus.FRAUDULENT: set(),
    VerificationStatus.FAILED: {VerificationStatus.PENDING},
}

COMPLAINT_TRANSITIONS: dict[str, set[str]] = {
    ComplaintStatus.DRAFT: {ComplaintStatus.SUBMITTED},
    ComplaintStatus.SUBMITTED: {
        ComplaintStatus.UNDER_REVIEW,
        ComplaintStatus.ESCALATED,
        ComplaintStatus.CLOSED,
    },
    ComplaintStatus.UNDER_REVIEW: {
        ComplaintStatus.ESCALATED,
        ComplaintStatus.RESOLVED,
        ComplaintStatus.CLOSED,
    },
    ComplaintStatus.ESCALATED: {
        ComplaintStatus.UNDER_REVIEW,
        ComplaintStatus.RESOLVED,
        ComplaintStatus.CLOSED,
    },
    ComplaintStatus.RESOLVED: {ComplaintStatus.CLOSED},
    ComplaintStatus.CLOSED: set(),
}


def can_transition(transitions: dict[str, set[str]], current: str, target: str) -> bool:
    if current == target:
        return True
    return target in transitions.get(current, set())
