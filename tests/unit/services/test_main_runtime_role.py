"""Unit tests for startup runtime-role behavior in ``src.main``."""

from __future__ import annotations

import pytest

from src.main import _pipeline_worker_disabled, _runtime_role, _scheduler_disabled


def test_runtime_role_defaults_to_all(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MED13_RUNTIME_ROLE", raising=False)
    assert _runtime_role() == "all"


def test_scheduler_disabled_for_api_role(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MED13_RUNTIME_ROLE", "api")
    monkeypatch.delenv("MED13_DISABLE_INGESTION_SCHEDULER", raising=False)
    assert _scheduler_disabled() is True


def test_scheduler_enabled_for_scheduler_role(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MED13_RUNTIME_ROLE", "scheduler")
    monkeypatch.delenv("MED13_DISABLE_INGESTION_SCHEDULER", raising=False)
    assert _scheduler_disabled() is False


def test_pipeline_worker_disabled_for_api_role(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MED13_RUNTIME_ROLE", "api")
    monkeypatch.delenv("MED13_DISABLE_PIPELINE_WORKER", raising=False)
    assert _pipeline_worker_disabled() is True


def test_pipeline_worker_enabled_for_scheduler_role(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MED13_RUNTIME_ROLE", "scheduler")
    monkeypatch.delenv("MED13_DISABLE_PIPELINE_WORKER", raising=False)
    assert _pipeline_worker_disabled() is False


def test_pipeline_worker_disable_flag_overrides_scheduler_role(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MED13_RUNTIME_ROLE", "scheduler")
    monkeypatch.setenv("MED13_DISABLE_PIPELINE_WORKER", "1")
    assert _pipeline_worker_disabled() is True


def test_disable_flag_overrides_scheduler_role(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MED13_RUNTIME_ROLE", "scheduler")
    monkeypatch.setenv("MED13_DISABLE_INGESTION_SCHEDULER", "1")
    assert _scheduler_disabled() is True


def test_runtime_role_rejects_invalid_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MED13_RUNTIME_ROLE", "worker")
    with pytest.raises(ValueError, match="Unsupported MED13_RUNTIME_ROLE"):
        _runtime_role()
