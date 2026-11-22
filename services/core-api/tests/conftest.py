"""Test bootstrap: configure settings before importing the app."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("DATABASE_URL", "postgresql://postgres:postgres@localhost:54322/postgres")
os.environ.setdefault("INTERNAL_JWT_SECRET", "test-internal-secret-at-least-32-chars")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-supabase-jwt-secret-at-least-32-chars")
os.environ.setdefault("SUPABASE_URL", "http://localhost:54321")
os.environ.setdefault("JWT_ISSUER", "http://localhost:54321/auth/v1")
os.environ.setdefault("JWT_AUDIENCE", "authenticated")
os.environ.setdefault("ENVIRONMENT", "test")
