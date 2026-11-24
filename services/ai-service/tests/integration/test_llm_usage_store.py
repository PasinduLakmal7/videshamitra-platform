"""PgUsageStore against a real ai schema. Requires TEST_DATABASE_URL (admin DSN)."""

from __future__ import annotations

import os
from decimal import Decimal
from uuid import uuid4

import asyncpg
import pytest

from app.db import migrate
from app.llm.base import CallMeta, Usage
from app.llm.usage import PgUsageStore

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not os.getenv("TEST_DATABASE_URL"), reason="set TEST_DATABASE_URL to an admin DSN"
    ),
]


@pytest.fixture
async def store_pool():
    admin = os.environ["TEST_DATABASE_URL"]
    await migrate.run(dsn=admin)
    # Prefer the least-privilege runtime role when its DSN is available.
    dsn = os.getenv("TEST_AI_DATABASE_URL") or admin
    pool = await asyncpg.create_pool(dsn, min_size=1, max_size=2)
    yield pool
    await pool.close()


async def test_record_updates_ledger_run_and_daily_total(store_pool):
    store = PgUsageStore(store_pool)
    tag = f"test-{uuid4().hex[:8]}"
    async with store_pool.acquire() as conn:
        run_id = await conn.fetchval(
            "insert into ai.analysis_runs (verification_id) values (gen_random_uuid()) returning id"
        )
    try:
        before = await store.tokens_used_today()
        usage = Usage("gemini-2.5-flash", 100, 20)
        await store.record(usage, Decimal("0.000080"), CallMeta(purpose=tag, run_id=run_id))
        await store.record(usage, Decimal("0.000080"), CallMeta(purpose=f"{tag}-chat"))
        assert await store.tokens_used_today() == before + 240

        async with store_pool.acquire() as conn:
            run = await conn.fetchrow(
                "select tokens_in, tokens_out, cost_usd, model from ai.analysis_runs where id = $1",
                run_id,
            )
            assert (run["tokens_in"], run["tokens_out"]) == (100, 20)
            assert run["cost_usd"] == Decimal("0.000080")
            assert run["model"] == "gemini-2.5-flash"
            rows = await conn.fetchval(
                "select count(*) from ai.llm_usage where run_id = $1", run_id
            )
            assert rows == 1
    finally:
        async with store_pool.acquire() as conn:
            await conn.execute(
                "delete from ai.llm_usage where purpose = any($1::text[])", [tag, f"{tag}-chat"]
            )
            await conn.execute("delete from ai.analysis_runs where id = $1", run_id)
