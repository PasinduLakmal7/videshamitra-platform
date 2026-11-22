"""Fetch SLBFE exports with timeout/retries and a checksum."""

from __future__ import annotations

import asyncio
import hashlib
import logging
from dataclasses import dataclass
from pathlib import Path

import httpx

from app.core.config import settings
from app.core.exceptions import UpstreamError
from app.integrations.slbfe.parser import ParseResult, parse_payload

logger = logging.getLogger(__name__)


@dataclass
class FetchedPayload:
    content: bytes
    content_type: str | None
    source_url: str
    checksum: str


async def fetch_source(source: str | None = None, *, api_key: str | None = None) -> FetchedPayload:
    source = source or settings.SLBFE_SOURCE_URL
    if not source:
        raise UpstreamError("SLBFE_SOURCE_URL is not configured", service="slbfe")

    path = Path(source)
    if await asyncio.to_thread(path.exists):
        content = await asyncio.to_thread(path.read_bytes)
        return FetchedPayload(
            content=content,
            content_type="application/octet-stream",
            source_url=str(path),
            checksum=hashlib.sha256(content).hexdigest(),
        )

    headers = {}
    key = api_key or settings.SLBFE_API_KEY
    if key:
        headers["Authorization"] = f"Bearer {key}"

    last_error: Exception | None = None
    for attempt in range(3):
        try:
            async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
                response = await client.get(source, headers=headers)
                response.raise_for_status()
                return FetchedPayload(
                    content=response.content,
                    content_type=response.headers.get("content-type"),
                    source_url=source,
                    checksum=hashlib.sha256(response.content).hexdigest(),
                )
        except Exception as exc:
            last_error = exc
            logger.warning(
                "slbfe_fetch_failed",
                extra={"attempt": attempt + 1, "error": str(exc)},
            )
            if attempt < 2:
                await asyncio.sleep(2**attempt)
    raise UpstreamError(
        "Could not fetch the SLBFE export", service="slbfe", details=str(last_error)
    )


async def fetch_and_parse(source: str | None = None) -> tuple[FetchedPayload, ParseResult]:
    fetched = await fetch_source(source)
    parsed = parse_payload(fetched.content, fetched.content_type)
    return fetched, parsed
