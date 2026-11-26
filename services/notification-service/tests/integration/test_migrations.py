from __future__ import annotations

import os

import asyncpg
import pytest
from asyncpg.exceptions import InsufficientPrivilegeError

from app.db.migrate import run

TEST_DSN = os.environ.get("TEST_DATABASE_URL", "")
pytestmark = pytest.mark.skipif(not TEST_DSN, reason="TEST_DATABASE_URL is not set")


async def test_migrations_are_idempotent_and_tables_exist():
    first = await run(dsn=TEST_DSN)
    second = await run(dsn=TEST_DSN)
    assert second == []
    assert "001_schema.sql" in first or first == []

    conn = await asyncpg.connect(TEST_DSN)
    try:
        tables = {
            row["tablename"]
            for row in await conn.fetch(
                "select tablename from pg_tables where schemaname = 'notification'"
            )
        }
    finally:
        await conn.close()
    assert {
        "device_tokens",
        "notification_preferences",
        "deliveries",
        "delivery_attempts",
        "event_dedupe",
        "schema_migrations",
    } <= tables


async def test_runtime_role_can_dml_but_not_create_or_read_registry():
    conn = await asyncpg.connect(TEST_DSN)
    try:
        await conn.execute("create schema if not exists core")
        await conn.execute("create table if not exists core.notification_isolation_probe (id int)")
        await conn.execute("set role notification_service_role")
        await conn.execute(
            """
            insert into notification.notification_preferences (user_id, channels)
            values ('00000000-0000-0000-0000-000000000001', '{"push": true}'::jsonb)
            on conflict (user_id) do nothing
            """
        )
        with pytest.raises(InsufficientPrivilegeError):
            await conn.execute("create table notification.should_fail (id int)")
        with pytest.raises(InsufficientPrivilegeError):
            await conn.fetch("select * from notification.schema_migrations")
        with pytest.raises(InsufficientPrivilegeError):
            await conn.fetch("select * from core.notification_isolation_probe")
    finally:
        await conn.close()
