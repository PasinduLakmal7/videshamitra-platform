#!/usr/bin/env python3
"""Import an SLBFE agency export.

Examples:
    python scripts/import_agencies.py --source ./fixtures/agencies.csv --dry-run
    python scripts/import_agencies.py --source https://example.lk/agencies.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import date
from pathlib import Path
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.logging import setup_logging  # noqa: E402
from app.db.pool import connect  # noqa: E402
from app.integrations.slbfe.import_service import SLBFEImporter  # noqa: E402


async def run(args: argparse.Namespace) -> int:
    conn = await connect()
    try:
        importer = SLBFEImporter()
        if args.dry_run:
            summary = await importer.import_from_source(
                conn,
                source=args.source,
                snapshot_date=args.date,
                dry_run=True,
            )
        else:
            async with conn.transaction():
                summary = await importer.import_from_source(
                    conn,
                    source=args.source,
                    snapshot_date=args.date,
                    imported_by=UUID(args.imported_by) if args.imported_by else None,
                )
        print(json.dumps(summary.as_dict(), indent=2))
        return 0
    finally:
        await conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Import agencies from SLBFE")
    parser.add_argument(
        "--source", default=None, help="URL or local file (default: SLBFE_SOURCE_URL)"
    )
    parser.add_argument(
        "--date", type=date.fromisoformat, default=None, help="snapshot date YYYY-MM-DD"
    )
    parser.add_argument("--imported-by", default=None, help="admin user UUID for audit")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    setup_logging()
    try:
        return asyncio.run(run(args))
    except Exception as exc:
        print(f"Import failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
