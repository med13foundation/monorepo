"""Unit tests for PostgreSQL row-level-security session context helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast
from uuid import uuid4

from src.database.session import set_session_rls_context

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


class _DialectStub:
    def __init__(self, name: str) -> None:
        self.name = name


class _BindStub:
    def __init__(self, dialect_name: str) -> None:
        self.dialect = _DialectStub(dialect_name)


class _RecordingSession:
    def __init__(self, dialect_name: str) -> None:
        self.bind = _BindStub(dialect_name)
        self.captured_values: list[str] = []

    def execute(self, statement: object, params: dict[str, str]) -> None:
        del statement
        self.captured_values.append(params["value"])


def test_set_session_rls_context_noops_for_non_postgres() -> None:
    session = _RecordingSession("sqlite")

    set_session_rls_context(
        cast("Session", session),
        current_user_id=uuid4(),
        has_phi_access=True,
        is_admin=True,
        bypass_rls=True,
    )

    assert session.captured_values == []


def test_set_session_rls_context_writes_expected_postgres_settings() -> None:
    session = _RecordingSession("postgresql")
    user_id = uuid4()

    set_session_rls_context(
        cast("Session", session),
        current_user_id=user_id,
        has_phi_access=True,
        is_admin=False,
        bypass_rls=False,
    )

    assert session.captured_values == [
        str(user_id),
        "true",
        "false",
        "false",
    ]
