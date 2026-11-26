from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas.preference import PreferencesOut, PreferencesUpdate
from app.services.preference_service import PreferenceService


class FakePreferenceRepo:
    def __init__(self):
        self.rows: dict = {}

    async def get(self, conn, user_id):
        return self.rows.get(user_id)

    async def upsert(
        self,
        conn,
        *,
        user_id,
        channels,
        quiet_hours_start,
        quiet_hours_end,
        timezone,
        locale,
    ):
        row = {
            "user_id": user_id,
            "channels": channels,
            "quiet_hours_start": quiet_hours_start,
            "quiet_hours_end": quiet_hours_end,
            "timezone": timezone,
            "locale": locale,
        }
        self.rows[user_id] = row
        return row


async def test_defaults_without_row():
    service = PreferenceService(repo=FakePreferenceRepo())
    prefs = await service.get(None, uuid4())
    assert prefs.channels["push"] is True
    assert prefs.channels["whatsapp"] is False
    assert prefs.timezone == "Asia/Colombo"


async def test_partial_update_merges_channels_and_quiet_hours():
    service = PreferenceService(repo=FakePreferenceRepo())
    user_id = uuid4()
    await service.update(None, user_id, PreferencesUpdate(channels={"whatsapp": True}))
    prefs = await service.update(
        None,
        user_id,
        PreferencesUpdate(quiet_hours_start="21:00", quiet_hours_end="07:00"),
    )
    assert prefs.channels["whatsapp"] is True
    assert prefs.channels["push"] is True
    assert prefs.quiet_hours_start == "21:00"
    assert prefs.quiet_hours_end == "07:00"


def test_unknown_channel_rejected():
    with pytest.raises(ValidationError):
        PreferencesUpdate(channels={"fax": True})


def test_quiet_hours_must_be_a_pair():
    with pytest.raises(ValidationError):
        PreferencesUpdate(quiet_hours_start="21:00")


def test_invalid_quiet_hour_rejected():
    with pytest.raises(ValidationError):
        PreferencesUpdate(quiet_hours_start="25:00", quiet_hours_end="07:00")


def test_out_merges_defaults():
    user_id = uuid4()
    prefs = PreferencesOut.from_record(
        user_id,
        {"channels": {"whatsapp": True}},
        {"push": True, "whatsapp": False, "email": False, "sms": False},
        "Asia/Colombo",
    )
    assert prefs.channels == {
        "push": True,
        "whatsapp": True,
        "email": False,
        "sms": False,
    }
