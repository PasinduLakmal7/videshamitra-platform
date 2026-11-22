"""Shared response envelopes, pagination primitives and helpers."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Generic, Literal, TypeVar

from fastapi import Query
from pydantic import BaseModel

from app.core.exceptions import BadRequest
from app.core.request_id import current_request_id

T = TypeVar("T")


class Meta(BaseModel):
    request_id: str


class PageMeta(Meta):
    page: int
    page_size: int
    total: int


class ApiResponse(BaseModel, Generic[T]):
    data: T
    meta: Meta


class PageResponse(BaseModel, Generic[T]):
    data: list[T]
    meta: PageMeta


class PageParams:
    """Validated `page`, `page_size`, `sort`, `order` query parameters."""

    def __init__(
        self,
        page: int = Query(default=1, ge=1),
        page_size: int = Query(default=20, ge=1, le=100),
        sort: str | None = Query(default=None),
        order: Literal["asc", "desc"] = Query(default="desc"),
    ) -> None:
        # Direct construction (tests/tools) can receive FastAPI `Query` default
        # objects; normalise them back to plain values.
        if not isinstance(page, int):
            page = 1
        if not isinstance(page_size, int):
            page_size = 20
        if not isinstance(sort, str):
            sort = None
        if order not in ("asc", "desc"):
            order = "desc"
        if page < 1:
            raise BadRequest("page must be at least 1", code="invalid_pagination")
        if page_size < 1 or page_size > 100:
            raise BadRequest("page_size must be between 1 and 100", code="invalid_pagination")
        self.page = page
        self.page_size = page_size
        self.sort = sort
        self.order = order

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size

    def resolve_sort(self, allowed: dict[str, str], default: str) -> str:
        if not self.sort:
            column = allowed[default]
        else:
            column = allowed.get(self.sort)
            if not column:
                raise BadRequest(
                    f"Unsupported sort field '{self.sort}'",
                    code="invalid_sort",
                    details={"allowed": sorted(allowed)},
                )
        direction = "ASC" if self.order == "asc" else "DESC"
        return f"{column} {direction}"


def ok(data: Any) -> dict[str, Any]:
    return {"data": data, "meta": {"request_id": current_request_id()}}


def page_data(items: Sequence[Any], total: int, params: PageParams) -> dict[str, Any]:
    return {
        "data": list(items),
        "meta": {
            "request_id": current_request_id(),
            "page": params.page,
            "page_size": params.page_size,
            "total": total,
        },
    }


class MessageData(BaseModel):
    message: str


class IdData(BaseModel):
    id: str


class CountData(BaseModel):
    count: int
