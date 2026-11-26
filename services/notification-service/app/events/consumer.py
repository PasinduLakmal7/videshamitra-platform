"""Redis stream consumer with dedupe-friendly handling and a dead-letter stream."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import socket
from collections.abc import Awaitable, Callable
from typing import Any

import redis.asyncio as redis

from app.core.config import settings
from app.core.request_id import trace_id_var
from app.events.envelope import InvalidEvent, dead_letter_stream, decode_from_stream

logger = logging.getLogger(__name__)

Handler = Callable[[dict[str, Any]], Awaitable[None]]

MAX_DELIVERY_ATTEMPTS = 5
CLAIM_IDLE_MS = 60_000


def consumer_name() -> str:
    return f"{settings.SERVICE_NAME}-{socket.gethostname()}-{os.getpid()}"


class StreamConsumer:
    def __init__(
        self,
        client: redis.Redis,
        stream: str,
        group: str,
        *,
        consumer: str | None = None,
        block_ms: int = 5_000,
        batch: int = 10,
    ) -> None:
        self.client = client
        self.stream = stream
        self.group = group
        self.consumer = consumer or consumer_name()
        self.block_ms = block_ms
        self.batch = batch
        self._running = False

    async def ensure_group(self) -> None:
        try:
            await self.client.xgroup_create(self.stream, self.group, id="0", mkstream=True)
            logger.info(
                "consumer_group_created",
                extra={"stream": self.stream, "group": self.group},
            )
        except redis.ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise

    async def _dead_letter(self, event: dict[str, Any] | None, error: str, message_id: str) -> None:
        payload = {"error": error, "message_id": message_id}
        if event is not None:
            payload["event"] = json.dumps(event, default=str)
        await self.client.xadd(
            dead_letter_stream(self.stream, settings.NOTIFICATION_DLQ_SUFFIX),
            payload,
            maxlen=settings.EVENT_MAX_LENGTH,
        )
        logger.error(
            "event_dead_lettered",
            extra={
                "event_id": str(event.get("event_id")) if event else None,
                "stream": self.stream,
                "error": error,
            },
        )

    async def _process_entry(
        self, message_id: str, fields: dict[str, Any], handler: Handler
    ) -> bool:
        try:
            event = decode_from_stream(fields)
        except Exception as exc:
            await self._dead_letter(None, f"decode_error:{type(exc).__name__}", message_id)
            await self.client.xack(self.stream, self.group, message_id)
            return False

        event_id = str(event.get("event_id", message_id))
        attempts = await self.client.hincrby(f"{self.stream}:attempts", event_id, 1)
        if attempts > MAX_DELIVERY_ATTEMPTS:
            await self._dead_letter(event, "max_attempts", message_id)
            await self.client.xack(self.stream, self.group, message_id)
            await self.client.hdel(f"{self.stream}:attempts", event_id)
            return False

        token = trace_id_var.set(str(event.get("trace_id", "")))
        try:
            await handler(event)
        except InvalidEvent as exc:
            await self._dead_letter(event, f"invalid_event:{exc}", message_id)
            await self.client.xack(self.stream, self.group, message_id)
            await self.client.hdel(f"{self.stream}:attempts", event_id)
            return False
        except Exception:
            logger.exception(
                "event_handler_failed",
                extra={"event_id": event_id, "stream": self.stream, "attempt": attempts},
            )
            return False
        finally:
            trace_id_var.reset(token)

        await self.client.xack(self.stream, self.group, message_id)
        await self.client.hdel(f"{self.stream}:attempts", event_id)
        return True

    async def _claim_stale(self, handler: Handler) -> None:
        try:
            claimed = await self.client.xautoclaim(
                self.stream,
                self.group,
                self.consumer,
                min_idle_time=CLAIM_IDLE_MS,
                start_id="0-0",
                count=self.batch,
            )
        except Exception:
            logger.exception("xautoclaim_failed", extra={"stream": self.stream})
            return
        messages = claimed[1] if len(claimed) > 1 else []
        for message_id, fields in messages:
            if fields:
                await self._process_entry(message_id, fields, handler)

    async def run(self, handler: Handler, stop_event: asyncio.Event | None = None) -> None:
        await self.ensure_group()
        self._running = True
        stop_event = stop_event or asyncio.Event()
        logger.info(
            "consumer_started",
            extra={"stream": self.stream, "group": self.group, "consumer": self.consumer},
        )
        try:
            while not stop_event.is_set():
                try:
                    response = await self.client.xreadgroup(
                        self.group,
                        self.consumer,
                        {self.stream: ">"},
                        count=self.batch,
                        block=self.block_ms,
                    )
                except asyncio.CancelledError:
                    raise
                except redis.TimeoutError:
                    # A read timeout during shutdown is expected; the stop check
                    # at the top of the loop exits cleanly.
                    continue
                except Exception:
                    logger.exception("xreadgroup_failed", extra={"stream": self.stream})
                    await asyncio.sleep(1)
                    continue

                if not response:
                    await self._claim_stale(handler)
                    continue

                for _stream, messages in response:
                    for message_id, fields in messages:
                        await self._process_entry(message_id, fields, handler)
        finally:
            self._running = False
            logger.info("consumer_stopped", extra={"stream": self.stream})

    def stop(self) -> None:
        self._running = False


def install_stop_handlers(stop_event: asyncio.Event) -> None:
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:  # pragma: no cover - Windows
            pass
