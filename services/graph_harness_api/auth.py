"""Authentication helpers for the standalone harness service."""

from __future__ import annotations

from fastapi import Depends, HTTPException, status

from src.domain.entities.user import User, UserRole
from src.routes.auth import get_current_active_user

_WRITE_ROLES = frozenset(
    {
        UserRole.ADMIN,
        UserRole.CURATOR,
        UserRole.RESEARCHER,
    },
)
_CURRENT_ACTIVE_USER_DEPENDENCY = Depends(get_current_active_user)


def get_current_harness_user(
    current_user: User = _CURRENT_ACTIVE_USER_DEPENDENCY,
) -> User:
    """Return the authenticated active user for harness requests."""
    return current_user


_CURRENT_HARNESS_USER_DEPENDENCY = Depends(get_current_harness_user)


def require_harness_read_access(
    current_user: User = _CURRENT_HARNESS_USER_DEPENDENCY,
) -> User:
    """Require authenticated access for harness read endpoints."""
    return current_user


def require_harness_write_access(
    current_user: User = _CURRENT_HARNESS_USER_DEPENDENCY,
) -> User:
    """Require researcher-or-higher access for harness mutations."""
    if current_user.role not in _WRITE_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Researcher, curator, or admin role required",
        )
    return current_user


__all__ = [
    "get_current_harness_user",
    "require_harness_read_access",
    "require_harness_write_access",
]
