"""Migration integration test. Requires TEST_DATABASE_URL and a disposable DB."""

from __future__ import annotations

import os

import asyncpg
import pytest

pytestmark = pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"),
    reason="set TEST_DATABASE_URL to a disposable Postgres database",
)


async def test_migrations_apply_and_tables_exist() -> None:
    dsn = os.environ["TEST_DATABASE_URL"]
    from app.db.migrate import run

    await run(dsn=dsn)
    # Idempotent second run.
    applied = await run(dsn=dsn)
    assert applied == []

    conn = await asyncpg.connect(dsn)
    try:
        tables = {
            row["tablename"]
            for row in await conn.fetch("select tablename from pg_tables where schemaname = 'core'")
        }
    finally:
        await conn.close()
    expected = {
        "users",
        "user_consents",
        "idempotency_keys",
        "outbox_events",
        "event_dedupe",
        "agency_snapshots",
        "agencies",
        "agency_license_history",
        "verifications",
        "documents",
        "migration_journeys",
        "checkins",
        "complaints",
        "complaint_documents",
        "case_notes",
        "notifications",
        "audit_logs",
        "schema_migrations",
    }
    assert expected <= tables
