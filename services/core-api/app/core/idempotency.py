"""Database-backed idempotency for mutating public requests.

Flow:
1. `begin_idempotency` reserves `(user_id, key)` with a processing marker.
2. The endpoint performs its work.
3. `complete_idempotency` stores the serialisable response payload.
4. On failure `abort_idempotency` releases the reservation.

Concurrent retries either replay the stored response or receive
`request_in_progress` (409) while the first request finishes.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import asyncpg

from app.core.config import settings
from app.core.exceptions import BadRequest, Conflict


@dataclass
class IdempotencyContext:
    key: str
    user_id: UUID
    method: str
    path: str
    request_hash: str
    acquired: bool = True
    replay: Any = None
    status_code: int = 200


def _hash_payload(payload: Any) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


async def begin_idempotency(
    conn: asyncpg.Connection,
    *,
    user_id: UUID,
    key: str | None,
    method: str,
    path: str,
    payload: Any,
) -> IdempotencyContext:
    key = (key or "").strip()
    if not key:
        raise BadRequest(
            "Idempotency-Key header is required for this endpoint",
            code="idempotency_key_required",
        )
    if len(key) > 255:
        raise BadRequest("Idempotency-Key is too long", code="idempotency_key_invalid")

    request_hash = _hash_payload(payload)
    inserted = await conn.fetchval(
        """
        insert into core.idempotency_keys
            (user_id, key, method, path, request_hash, status_code, expires_at)
        values ($1, $2, $3, $4, $5, 0,
                now() + make_interval(hours => $6))
        on conflict (user_id, key) do nothing
        returning id
        """,
        user_id,
        key,
        method,
        path,
        request_hash,
        settings.IDEMPOTENCY_TTL_HOURS,
    )
    ctx = IdempotencyContext(
        key=key,
        user_id=user_id,
        method=method,
        path=path,
        request_hash=request_hash,
        acquired=inserted is not None,
    )
    if ctx.acquired:
        return ctx

    row = await conn.fetchrow(
        """
        select request_hash, status_code, response_body
        from core.idempotency_keys
        where user_id = $1 and key = $2
        """,
        user_id,
        key,
    )
    if row is None:  # pragma: no cover - reservation row deleted concurrently
        raise Conflict("Idempotency key state changed; retry", code="idempotency_conflict")
    if row["request_hash"] != request_hash:
        raise Conflict(
            "Idempotency-Key was already used with a different payload",
            code="idempotency_key_reused",
        )
    if row["status_code"] == 0:
        raise Conflict(
            "A request with this Idempotency-Key is still in progress",
            code="request_in_progress",
        )
    ctx.acquired = False
    ctx.replay = row["response_body"]
    ctx.status_code = int(row["status_code"])
    return ctx


async def complete_idempotency(
    conn: asyncpg.Connection,
    ctx: IdempotencyContext,
    payload: Any,
    *,
    status_code: int = 200,
) -> None:
    if not ctx.acquired:
        return
    await conn.execute(
        """
        update core.idempotency_keys
        set status_code = $3, response_body = $4
        where user_id = $1 and key = $2
        """,
        ctx.user_id,
        ctx.key,
        status_code,
        json.loads(json.dumps(payload, default=str)),
    )


async def abort_idempotency(conn: asyncpg.Connection, ctx: IdempotencyContext) -> None:
    if not ctx.acquired:
        return
    await conn.execute(
        """
        delete from core.idempotency_keys
        where user_id = $1 and key = $2 and status_code = 0
        """,
        ctx.user_id,
        ctx.key,
    )


async def cleanup_expired(conn: asyncpg.Connection) -> int:
    result = await conn.execute("delete from core.idempotency_keys where expires_at < now()")
    try:
        return int(result.split()[-1])
    except (ValueError, IndexError):
        return 0
