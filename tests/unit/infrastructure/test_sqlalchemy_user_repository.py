"""
Unit tests for SqlAlchemyUserRepository compatibility behavior.
"""

from sqlalchemy.dialects import sqlite

from src.domain.entities.user import UserStatus
from src.infrastructure.repositories.sqlalchemy_user_repository import (
    SqlAlchemyUserRepository,
)


def _compile_filter_sql(status: UserStatus) -> str:
    expression = SqlAlchemyUserRepository._status_filter(status)
    return str(
        expression.compile(
            dialect=sqlite.dialect(),
            compile_kwargs={"literal_binds": True},
        ),
    )


def test_status_filter_for_inactive_avoids_enum_label_lock_in() -> None:
    sql = _compile_filter_sql(UserStatus.INACTIVE)
    assert "NOT IN" in sql
    assert "ACTIVE" in sql
    assert "SUSPENDED" in sql
    assert "PENDING_VERIFICATION" in sql
    assert "INACTIVE" not in sql
    assert "DEACTIVATED" not in sql


def test_status_filter_for_active_remains_specific() -> None:
    sql = _compile_filter_sql(UserStatus.ACTIVE)
    assert "ACTIVE" in sql
    assert "DEACTIVATED" not in sql
