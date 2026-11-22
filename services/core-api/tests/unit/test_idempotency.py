"""Idempotency reservation/replay behaviour with an in-memory connection."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest

from app.core.exceptions import BadRequest, Conflict
from app.core.idempotency import (
    abort_idempotency,
    begin_idempotency,
    complete_idempotency,
)

USER_ID = UUID("11111111-1111-1111-1111-111111111111")


class FakeIdempotencyConn:
    def __init__(self) -> None:
        self.row: dict[str, Any] | None = None

    async def fetchval(self, sql: str, *args: Any) -> Any:
        if "insert into core.idempotency_keys" in sql:
            if self.row is not None:
                return None
            self.row = {
                "user_id": args[0],
                "key": args[1],
                "request_hash": args[4],
                "status_code": 0,
                "response_body": None,
            }
            return uuid4()
        return None

    async def fetchrow(self, sql: str, *args: Any) -> Any:
        if self.row is None:
            return None
        return dict(self.row)

    async def execute(self, sql: str, *args: Any) -> str:
        if "set status_code" in sql and self.row is not None:
            self.row["status_code"] = args[2]
            self.row["response_body"] = args[3]
            return "UPDATE 1"
        if "delete from core.idempotency_keys" in sql:
            self.row = None
            return "DELETE 1"
        return "OK"


async def test_missing_key_rejected() -> None:
    conn = FakeIdempotencyConn()
    with pytest.raises(BadRequest) as exc:
        await begin_idempotency(
            conn,  # type: ignore[arg-type]
            user_id=USER_ID,
            key=None,
            method="POST",
            path="/api/v1/verification",
            payload={},
        )
    assert exc.value.code == "idempotency_key_required"


async def test_replay_returns_stored_response() -> None:
    conn = FakeIdempotencyConn()
    payload = {"a": 1}
    first = await begin_idempotency(
        conn,  # type: ignore[arg-type]
        user_id=USER_ID,
        key="key-1",
        method="POST",
        path="/api/v1/verification",
        payload=payload,
    )
    assert first.acquired is True
    await complete_idempotency(
        conn,
        first,
        {"id": "abc"},
        status_code=202,  # type: ignore[arg-type]
    )

    second = await begin_idempotency(
        conn,  # type: ignore[arg-type]
        user_id=USER_ID,
        key="key-1",
        method="POST",
        path="/api/v1/verification",
        payload=payload,
    )
    assert second.acquired is False
    assert second.replay == {"id": "abc"}
    assert second.status_code == 202


async def test_reuse_with_different_payload_conflicts() -> None:
    conn = FakeIdempotencyConn()
    await begin_idempotency(
        conn,  # type: ignore[arg-type]
        user_id=USER_ID,
        key="key-2",
        method="POST",
        path="/x",
        payload={"a": 1},
    )
    with pytest.raises(Conflict) as exc:
        await begin_idempotency(
            conn,  # type: ignore[arg-type]
            user_id=USER_ID,
            key="key-2",
            method="POST",
            path="/x",
            payload={"a": 2},
        )
    assert exc.value.code == "idempotency_key_reused"


async def test_in_progress_conflicts() -> None:
    conn = FakeIdempotencyConn()
    await begin_idempotency(
        conn,  # type: ignore[arg-type]
        user_id=USER_ID,
        key="key-3",
        method="POST",
        path="/x",
        payload={"a": 1},
    )
    with pytest.raises(Conflict) as exc:
        await begin_idempotency(
            conn,  # type: ignore[arg-type]
            user_id=USER_ID,
            key="key-3",
            method="POST",
            path="/x",
            payload={"a": 1},
        )
    assert exc.value.code == "request_in_progress"


async def test_abort_releases_reservation() -> None:
    conn = FakeIdempotencyConn()
    ctx = await begin_idempotency(
        conn,  # type: ignore[arg-type]
        user_id=USER_ID,
        key="key-4",
        method="POST",
        path="/x",
        payload={},
    )
    await abort_idempotency(conn, ctx)  # type: ignore[arg-type]
    assert conn.row is None
