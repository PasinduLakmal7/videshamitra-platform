"""Role/permission predicates shared by dependencies and services."""

from __future__ import annotations

from app.core.exceptions import Forbidden
from app.models.entities import CurrentUser
from app.models.enums import UserRole


def is_staff(user: CurrentUser) -> bool:
    return user.role in (UserRole.CASEWORKER, UserRole.ADMIN)


def is_admin(user: CurrentUser) -> bool:
    return user.role == UserRole.ADMIN


def require_staff(user: CurrentUser) -> None:
    if not is_staff(user):
        raise Forbidden("Staff access required")


def require_admin(user: CurrentUser) -> None:
    if not is_admin(user):
        raise Forbidden("Admin access required")


def require_owner_or_staff(user: CurrentUser, owner_id) -> None:
    if user.id != owner_id and not is_staff(user):
        raise Forbidden("You do not have access to this resource")
