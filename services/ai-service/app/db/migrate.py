"""Idempotent SQL migration runner for the ai schema (run with an admin DSN).

python -m app.db.migrate [--status] [--dsn DSN]
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import logging
import sys
from pathlib import Path

import asyncpg

from app.core.config import settings
from app.core.logging import setup_logging

logger = logging.getLogger("migrate")

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"
LOCK_KEY = 0x56494441495343  # distinct from core's lock


def migration_dsn(override: str | None = None) -> str:
    dsn = override or settings.MIGRATION_DATABASE_URL or settings.DATABASE_URL
    if not dsn:
        raise RuntimeError("Set --dsn, MIGRATION_DATABASE_URL or DATABASE_URL")
    return dsn


def migration_files() -> list[Path]:
    return sorted(MIGRATIONS_DIR.glob("*.sql"))


def _checksum(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


async def _ensure_registry(conn: asyncpg.Connection) -> None:
    await conn.execute("create schema if not exists ai")
    await conn.execute(
        """
        create table if not exists ai.schema_migrations (
            filename text primary key,
            checksum text not null,
            applied_at timestamptz not null default now()
        )
        """
    )


async def run(dsn: str | None = None, status_only: bool = False) -> list[str]:
    conn = await asyncpg.connect(migration_dsn(dsn))
    applied_now: list[str] = []
    try:
        await conn.execute("select pg_advisory_lock($1)", LOCK_KEY)
        await _ensure_registry(conn)
        rows = await conn.fetch("select filename, checksum from ai.schema_migrations")
        applied = {row["filename"]: row["checksum"] for row in rows}
        for path in migration_files():
            checksum = await asyncio.to_thread(_checksum, path)
            if path.name in applied:
                if applied[path.name] != checksum:
                    raise RuntimeError(
                        f"Applied migration {path.name} changed on disk; add a new one instead"
                    )
                if status_only:
                    logger.info("migration_applied", extra={"file": path.name})
                continue
            if status_only:
                logger.info("migration_pending", extra={"file": path.name})
                continue
            logger.info("migration_start", extra={"file": path.name})
            sql = await asyncio.to_thread(path.read_text, encoding="utf-8")
            async with conn.transaction():
                await conn.execute(sql)
                await conn.execute(
                    "insert into ai.schema_migrations (filename, checksum) values ($1, $2)",
                    path.name,
                    checksum,
                )
            applied_now.append(path.name)
        return applied_now
    finally:
        try:
            await conn.execute("select pg_advisory_unlock($1)", LOCK_KEY)
        finally:
            await conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply ai-service migrations")
    parser.add_argument("--status", action="store_true", help="list applied/pending files")
    parser.add_argument("--dsn", default=None, help="admin DSN (overrides env)")
    args = parser.parse_args()
    setup_logging()
    try:
        applied = asyncio.run(run(dsn=args.dsn, status_only=args.status))
    except Exception as exc:
        logger.error("migration_failed", extra={"error": type(exc).__name__, "detail": str(exc)})
        return 1
    logger.info("migrations_applied", extra={"count": len(applied), "files": applied})
    return 0


if __name__ == "__main__":
    sys.exit(main())
