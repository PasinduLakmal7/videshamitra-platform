"""Check-in scheduler, missed escalation and stale verification recovery."""

from __future__ import annotations

import asyncio
import logging

from app.core.config import settings
from app.core.logging import setup_logging
from app.db.pool import acquire, close_pool, create_pool
from app.services.migration_service import MigrationService
from app.services.verification_service import VerificationService

logger = logging.getLogger(__name__)


async def run_once() -> None:
    async with acquire() as conn:
        try:
            await MigrationService().send_due_checkins(conn)
        except Exception:
            logger.exception("checkin_send_failed")
        try:
            await MigrationService().escalate_missed(conn)
        except Exception:
            logger.exception("checkin_escalation_failed")
        try:
            await VerificationService().recover_stale(conn)
        except Exception:
            logger.exception("stale_verification_recovery_failed")


async def main() -> None:
    setup_logging()
    await create_pool()
    try:
        while True:
            await run_once()
            await asyncio.sleep(settings.CHECKIN_SCHEDULER_INTERVAL_SECONDS)
    finally:
        await close_pool()


if __name__ == "__main__":
    asyncio.run(main())
