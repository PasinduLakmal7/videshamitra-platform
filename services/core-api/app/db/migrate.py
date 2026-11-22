"""Idempotent SQL migration runner.

Usage:
    python -m app.db.migrate            # apply pending migrations
    python -m app.db.migrate --status   # show applied files
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
LOCK_KEY = 0x56494445534841  # "VIDESHA"


async def ensure_registry(conn: asyncpg.Connection) -> None:
    await conn.execute("create schema if not exists core")
    await conn.execute(
        """
        create table if not exists core.schema_migrations (
            filename text primary key,
            checksum text not null,
            applied_at timestamptz not null default now()
        )
        """
    )


def _checksum(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


async def applied_migrations(conn: asyncpg.Connection) -> dict[str, str]:
    rows = await conn.fetch("select filename, checksum from core.schema_migrations")
    return {row["filename"]: row["checksum"] for row in rows}


async def run(dsn: str | None = None, status_only: bool = False) -> list[str]:
    dsn = dsn or settings.DATABASE_URL
    conn = await asyncpg.connect(dsn)
    applied_now: list[str] = []
    try:
        await ensure_registry(conn)
        await conn.execute("select pg_advisory_lock($1)", LOCK_KEY)
        applied = await applied_migrations(conn)
        files = sorted(MIGRATIONS_DIR.glob("*.sql"))
        if not files:
            logger.warning("no_migrations_found", extra={"path": str(MIGRATIONS_DIR)})
            return applied_now

        for path in files:
            checksum = await asyncio.to_thread(_checksum, path)
            if path.name in applied:
                if applied[path.name] != checksum:
                    raise RuntimeError(
                        f"Applied migration {path.name} changed on disk. "
                        "Never edit applied migrations; add a new one."
                    )
                if status_only:
                    logger.info("migration_applied", extra={"file": path.name})
                continue
            if status_only:
                logger.info("migration_pending", extra={"file": path.name})
                continue
            logger.info("migration_start", extra={"file": path.name})
            async with conn.transaction():
                await conn.execute(path.read_text(encoding="utf-8"))
                await conn.execute(
                    "insert into core.schema_migrations (filename, checksum) values ($1, $2)",
                    path.name,
                    checksum,
                )
            applied_now.append(path.name)
            logger.info("migration_done", extra={"file": path.name})
        return applied_now
    finally:
        try:
            await conn.execute("select pg_advisory_unlock($1)", LOCK_KEY)
        finally:
            await conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply core-api migrations")
    parser.add_argument("--status", action="store_true", help="list applied/pending files")
    parser.add_argument("--dsn", default=None, help="override DATABASE_URL")
    args = parser.parse_args()
    setup_logging()
    try:
        applied = asyncio.run(run(dsn=args.dsn, status_only=args.status))
    except Exception as exc:  # pragma: no cover - CLI failure path
        logger.error("migration_failed", extra={"error": str(exc)})
        return 1
    if applied:
        logger.info("migrations_applied", extra={"count": len(applied), "files": applied})
    return 0


if __name__ == "__main__":
    sys.exit(main())
