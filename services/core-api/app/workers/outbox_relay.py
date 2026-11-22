"""Outbox relay loop entry point."""

from __future__ import annotations

import asyncio
import logging

from app.core.logging import setup_logging
from app.events.consumer import install_stop_handlers
from app.events.publisher import run_relay

logger = logging.getLogger(__name__)


async def main() -> None:
    setup_logging()
    stop = asyncio.Event()
    install_stop_handlers(stop)
    await run_relay(stop)


if __name__ == "__main__":
    asyncio.run(main())
