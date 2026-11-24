"""ai schema migrations and role isolation. Requires TEST_DATABASE_URL (admin DSN)."""

from __future__ import annotations

import os
from uuid import uuid4

import asyncpg
import pytest

from app.db import migrate, pool

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not os.getenv("TEST_DATABASE_URL"), reason="set TEST_DATABASE_URL to an admin DSN"
    ),
]

EXPECTED_TABLES = {
    "schema_migrations",
    "analysis_runs",
    "agent_traces",
    "document_extractions",
    "event_dedupe",
    "fee_rules",
    "wage_floors",
    "red_flag_rules",
    "chat_sessions",
    "chat_messages",
}


@pytest.fixture
async def conn():
    dsn = os.environ["TEST_DATABASE_URL"]
    await migrate.run(dsn=dsn)
    connection = await asyncpg.connect(dsn)
    yield connection
    await connection.close()


async def test_migrations_idempotent_and_tables_exist(conn):
    assert await migrate.run(dsn=os.environ["TEST_DATABASE_URL"]) == []
    tables = {
        row["tablename"]
        for row in await conn.fetch("select tablename from pg_tables where schemaname = 'ai'")
    }
    assert EXPECTED_TABLES <= tables


async def test_edited_migration_is_refused(conn):
    name = migrate.migration_files()[0].name
    original = await conn.fetchval(
        "select checksum from ai.schema_migrations where filename = $1", name
    )
    await conn.execute(
        "update ai.schema_migrations set checksum = 'tampered' where filename = $1", name
    )
    try:
        with pytest.raises(RuntimeError, match="changed on disk"):
            await migrate.run(dsn=os.environ["TEST_DATABASE_URL"])
    finally:
        await conn.execute(
            "update ai.schema_migrations set checksum = $2 where filename = $1", name, original
        )


async def test_rules_seeded_as_demo(conn):
    for table in ("fee_rules", "wage_floors", "red_flag_rules"):
        rows = await conn.fetch(f"select source from ai.{table}")
        assert rows, table
        assert all(row["source"].startswith("DEMO DATA") for row in rows), table
    missing = await conn.fetchval(
        "select count(*) from ai.red_flag_rules "
        "where description_si = '' or description_ta = '' or description_en = ''"
    )
    assert missing == 0


async def _assert_role_isolated(role_conn: asyncpg.Connection) -> None:
    assert await role_conn.fetchval("select current_user") == "ai_service_role"
    for denied in (
        "select * from core.users limit 1",
        "create table ai.should_not_exist (id int)",
        "select * from ai.schema_migrations",
    ):
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            async with role_conn.transaction():
                await role_conn.execute(denied)

    run_id = await role_conn.fetchval(
        "insert into ai.analysis_runs (verification_id) values ($1) returning id", uuid4()
    )
    session_id = await role_conn.fetchval(
        "insert into ai.chat_sessions (user_id) values ($1) returning id", uuid4()
    )
    await role_conn.execute(
        "insert into ai.chat_messages (session_id, role, content_redacted) "
        "values ($1, 'user', 'hello')",
        session_id,
    )
    assert await role_conn.fetchval("select count(*) from ai.red_flag_rules") > 0
    await role_conn.execute("delete from ai.analysis_runs where id = $1", run_id)
    await role_conn.execute("delete from ai.chat_sessions where id = $1", session_id)


async def test_runtime_role_is_isolated_to_ai(conn):
    # Supabase's postgres cannot SET ROLE, so log in as the role when its DSN is given.
    runtime_dsn = os.getenv("TEST_AI_DATABASE_URL")
    role_conn = await asyncpg.connect(runtime_dsn) if runtime_dsn else conn
    tx = role_conn.transaction()
    await tx.start()
    try:
        if not runtime_dsn:
            await conn.execute("create schema if not exists core")
            await conn.execute("create table if not exists core.users (id uuid primary key)")
            await conn.execute("set local role ai_service_role")
        await _assert_role_isolated(role_conn)
    finally:
        await tx.rollback()
        if runtime_dsn:
            await role_conn.close()


async def test_only_redacted_text_columns(conn):
    rows = await conn.fetch(
        """
        select table_name, column_name from information_schema.columns
        where table_schema = 'ai' and data_type = 'text'
          and (column_name like '%text%' or column_name like '%content%'
               or column_name like '%body%')
        """
    )
    assert rows
    for row in rows:
        assert row["column_name"].endswith("_redacted"), dict(row)


async def test_pool_search_path_is_ai(conn, monkeypatch):
    monkeypatch.setattr(pool, "_pool", None)
    created = await pool.create_pool(os.environ["TEST_DATABASE_URL"])
    try:
        async with pool.acquire() as pooled:
            assert await pooled.fetchval("show search_path") == "ai"
            assert await pooled.fetchval("select count(*) from red_flag_rules") > 0
    finally:
        await created.close()
        monkeypatch.setattr(pool, "_pool", None)
