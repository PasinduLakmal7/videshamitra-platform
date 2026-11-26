"""FastAPI dependencies."""

from __future__ import annotations

from app.core.internal_auth import require_core
from app.db.pool import get_connection

__all__ = ["get_connection", "require_core"]
