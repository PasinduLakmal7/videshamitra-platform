from __future__ import annotations

from uuid import uuid4

import pytest

from app.services.device_service import DeviceService


class FakeTransaction:
    async def __aenter__(self):
        return None

    async def __aexit__(self, *args):
        return False


class FakeConn:
    def transaction(self):
        return FakeTransaction()


class FakeDeviceRepo:
    def __init__(self):
        self.rows: dict[str, dict] = {}
        self.deactivated: list[str] = []

    async def get_by_token(self, conn, token):
        return self.rows.get(token)

    async def upsert(self, conn, *, user_id, token, platform, app_version, device_id, locale):
        row = self.rows.get(token) or {}
        row.update(
            {
                "id": row.get("id", uuid4()),
                "user_id": user_id,
                "token": token,
                "platform": platform,
                "app_version": app_version,
                "device_id": device_id,
                "locale": locale,
                "is_active": True,
            }
        )
        self.rows[token] = row
        return row

    async def count_active(self, conn, user_id):
        return sum(
            1 for row in self.rows.values() if row["user_id"] == user_id and row["is_active"]
        )

    async def deactivate_oldest(self, conn, user_id, *, exclude_id=None):
        candidates = [
            row
            for row in self.rows.values()
            if row["user_id"] == user_id and row["is_active"] and row["id"] != exclude_id
        ]
        if not candidates:
            return None
        row = candidates[0]
        row["is_active"] = False
        self.deactivated.append(row["token"])
        return row

    async def deactivate_by_id(self, conn, device_id):
        for row in self.rows.values():
            if row["id"] == device_id:
                row["is_active"] = False
                return row
        return None


async def test_register_upserts_and_reassigns():
    repo = FakeDeviceRepo()
    service = DeviceService(repo=repo)
    user_a, user_b = uuid4(), uuid4()
    first = await service.register(
        FakeConn(),
        user_id=user_a,
        token="token-1",
        platform="android",
        app_version="1.0",
        device_id="device-1",
        locale="si",
    )
    assert first["user_id"] == user_a
    second = await service.register(
        FakeConn(),
        user_id=user_b,
        token="token-1",
        platform="ios",
        app_version="2.0",
        device_id="device-1",
        locale="en",
    )
    assert second["user_id"] == user_b
    assert len(repo.rows) == 1


async def test_device_cap_evicts_oldest(monkeypatch):
    from app.services import device_service

    monkeypatch.setattr(device_service.settings, "MAX_DEVICES_PER_USER", 2)
    repo = FakeDeviceRepo()
    service = DeviceService(repo=repo)
    user_id = uuid4()
    for index in range(3):
        await service.register(
            FakeConn(),
            user_id=user_id,
            token=f"token-{index}",
            platform="android",
            app_version=None,
            device_id=None,
            locale=None,
        )
    active = [row for row in repo.rows.values() if row["is_active"]]
    assert len(active) == 2
    assert repo.deactivated


async def test_unregister_other_user_is_not_found():
    from app.core.errors import NotFound

    repo = FakeDeviceRepo()
    service = DeviceService(repo=repo)
    owner, other = uuid4(), uuid4()
    await service.register(
        FakeConn(),
        user_id=owner,
        token="token-1",
        platform="android",
        app_version=None,
        device_id=None,
        locale=None,
    )
    with pytest.raises(NotFound):
        await service.unregister(FakeConn(), user_id=other, token="token-1")


async def test_unregister_missing_is_idempotent():
    service = DeviceService(repo=FakeDeviceRepo())
    await service.unregister(FakeConn(), user_id=uuid4(), token="missing")
