"""Case-management facade.

Casework (queue, detail, assignment, notes, escalation) lives on
`ComplaintService` because complaints and cases share one aggregate. This
subclass keeps the CORE-32 service boundary explicit for admin routes and
future case-only behaviour.
"""

from __future__ import annotations

from app.services.complaint_service import ComplaintService


class CaseService(ComplaintService):
    """Caseworker-facing operations over the complaint/case aggregate."""
