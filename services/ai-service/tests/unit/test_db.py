from __future__ import annotations

import re

import pytest

from app.core.config import settings
from app.db import migrate, pool


def test_migration_files_are_numbered_and_unique():
    names = [path.name for path in migrate.migration_files()]
    assert names, "no migrations found"
    numbers = [re.match(r"^(\d{3})_[a-z0-9_]+\.sql$", name) for name in names]
    assert all(numbers), names
    prefixes = [match.group(1) for match in numbers]
    assert len(prefixes) == len(set(prefixes))
    assert names == sorted(names)


def test_migration_dsn_precedence(monkeypatch):
    monkeypatch.setattr(settings, "DATABASE_URL", "postgresql://runtime")
    monkeypatch.setattr(settings, "MIGRATION_DATABASE_URL", "")
    assert migrate.migration_dsn() == "postgresql://runtime"
    monkeypatch.setattr(settings, "MIGRATION_DATABASE_URL", "postgresql://admin")
    assert migrate.migration_dsn() == "postgresql://admin"
    assert migrate.migration_dsn("postgresql://cli") == "postgresql://cli"


def test_migration_dsn_required(monkeypatch):
    monkeypatch.setattr(settings, "DATABASE_URL", "")
    monkeypatch.setattr(settings, "MIGRATION_DATABASE_URL", "")
    with pytest.raises(RuntimeError):
        migrate.migration_dsn()


async def test_pool_uses_ai_search_path(monkeypatch):
    captured = {}

    async def fake_create_pool(**kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(pool.asyncpg, "create_pool", fake_create_pool)
    monkeypatch.setattr(pool, "_pool", None)
    await pool.create_pool("postgresql://runtime")
    assert captured["server_settings"] == {"search_path": "ai"}
    assert captured["dsn"] == "postgresql://runtime"
    assert captured["command_timeout"] == settings.DATABASE_COMMAND_TIMEOUT
    monkeypatch.setattr(pool, "_pool", None)


async def test_pool_requires_dsn(monkeypatch):
    monkeypatch.setattr(pool, "_pool", None)
    monkeypatch.setattr(settings, "DATABASE_URL", "")
    with pytest.raises(RuntimeError):
        await pool.create_pool()
