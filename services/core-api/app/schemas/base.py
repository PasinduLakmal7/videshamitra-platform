"""Base schema helpers."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class APIModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="ignore")

    @classmethod
    def from_record(cls, row: Any):
        return cls.model_validate(dict(row))
