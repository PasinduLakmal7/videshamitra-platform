"""Agency license watchdog: notify affected workers of license changes."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from app.core.config import settings
from app.core.logging import setup_logging
from app.db.pool import acquire, close_pool, create_pool
from app.services.agency_service import AgencyService

logger = logging.getLogger(__name__)


async def run_once(since: datetime | None = None) -> int:
    async with acquire() as conn:
        return await AgencyService().process_license_changes(conn, since=since)


async def main() -> None:
    setup_logging()
    await create_pool()
    since = datetime.now(UTC) - timedelta(days=1)
    try:
        while True:
            try:
                since = datetime.now(UTC) - timedelta(
                    seconds=settings.AGENCY_MONITOR_INTERVAL_SECONDS * 2
                )
                await run_once(since)
            except Exception:
                logger.exception("agency_monitor_failed")
            await asyncio.sleep(settings.AGENCY_MONITOR_INTERVAL_SECONDS)
    finally:
        await close_pool()


if __name__ == "__main__":
    asyncio.run(main())
