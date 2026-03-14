from __future__ import annotations

import warnings
from datetime import UTC, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool

from tests.sqlite_utils import (
    DEFAULT_BUSY_TIMEOUT_MS,
    build_sqlite_connect_args,
    configure_sqlite_engine,
)


def test_configure_sqlite_engine_sets_pragmas(tmp_path: Path) -> None:
    """Ensure our SQLite helper configures WAL, busy timeout, and synchronous mode."""
    db_path = tmp_path / "test.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args=build_sqlite_connect_args(),
        poolclass=NullPool,
    )
    configure_sqlite_engine(engine)

    with engine.connect() as connection:
        journal_mode = connection.execute(text("PRAGMA journal_mode;")).scalar()
        busy_timeout = connection.execute(text("PRAGMA busy_timeout;")).scalar()
        synchronous_level = connection.execute(text("PRAGMA synchronous;")).scalar()
        foreign_keys = connection.execute(text("PRAGMA foreign_keys;")).scalar()

    assert journal_mode.lower() == "wal"
    assert busy_timeout == DEFAULT_BUSY_TIMEOUT_MS
    # NORMAL synchronous level is 1
    assert synchronous_level == 1
    assert foreign_keys == 1


def test_configure_sqlite_engine_registers_datetime_adapters(tmp_path: Path) -> None:
    db_path = tmp_path / "datetime.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args=build_sqlite_connect_args(),
        poolclass=NullPool,
    )
    configure_sqlite_engine(engine)

    with warnings.catch_warnings():
        warnings.filterwarnings(
            "error",
            message="The default datetime adapter is deprecated.*",
            category=DeprecationWarning,
        )
        with engine.connect() as connection:
            result = connection.execute(
                text("SELECT :moment"),
                {"moment": datetime(2026, 3, 14, 12, 30, tzinfo=UTC)},
            )
            scalar_value = result.scalar()

    assert str(scalar_value) == "2026-03-14 12:30:00+00:00"
