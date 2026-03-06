from __future__ import annotations

import pytest

from src.database.engine_config import build_engine_kwargs


def test_build_engine_kwargs_uses_request_concurrency_postgres_pool_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("MED13_DB_POOL_SIZE", raising=False)
    monkeypatch.delenv("MED13_DB_MAX_OVERFLOW", raising=False)
    monkeypatch.delenv("MED13_DB_POOL_TIMEOUT_SECONDS", raising=False)
    monkeypatch.delenv("MED13_DB_POOL_RECYCLE_SECONDS", raising=False)
    monkeypatch.delenv("MED13_DB_POOL_USE_LIFO", raising=False)

    kwargs = build_engine_kwargs("postgresql://postgres:postgres@localhost:5432/test")

    assert kwargs == {
        "pool_pre_ping": True,
        "pool_size": 10,
        "max_overflow": 10,
        "pool_timeout": 30,
        "pool_recycle": 1800,
        "pool_use_lifo": True,
    }


def test_build_engine_kwargs_skips_pool_limits_for_sqlite() -> None:
    kwargs = build_engine_kwargs("sqlite:///test.db")

    assert kwargs == {"pool_pre_ping": True}


def test_build_engine_kwargs_honors_explicit_env_overrides(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MED13_DB_POOL_SIZE", "4")
    monkeypatch.setenv("MED13_DB_MAX_OVERFLOW", "1")
    monkeypatch.setenv("MED13_DB_POOL_TIMEOUT_SECONDS", "12")
    monkeypatch.setenv("MED13_DB_POOL_RECYCLE_SECONDS", "600")
    monkeypatch.setenv("MED13_DB_POOL_USE_LIFO", "false")

    kwargs = build_engine_kwargs(
        "postgresql+asyncpg://postgres:postgres@localhost/test",
    )

    assert kwargs == {
        "pool_pre_ping": True,
        "pool_size": 4,
        "max_overflow": 1,
        "pool_timeout": 12,
        "pool_recycle": 600,
        "pool_use_lifo": False,
    }


def test_build_engine_kwargs_rejects_negative_pool_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MED13_DB_POOL_SIZE", "-1")

    with pytest.raises(ValueError, match="MED13_DB_POOL_SIZE"):
        build_engine_kwargs("postgresql://postgres:postgres@localhost:5432/test")
