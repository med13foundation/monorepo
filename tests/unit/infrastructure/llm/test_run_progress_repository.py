"""Tests for Artana run-progress status normalization helpers."""

from __future__ import annotations

from dataclasses import dataclass

from src.infrastructure.llm.state.run_progress_repository import (
    _resolve_effective_status,
)


@dataclass
class _StubRunStatus:
    status: str
    last_event_type: str
    failure_reason: str | None = None
    blocked_on: str | None = None
    last_event_outcome: str | None = None


def test_resolve_effective_status_marks_run_summary_as_completed() -> None:
    status = _resolve_effective_status(
        progress_status="running",
        percent=0,
        run_status=_StubRunStatus(
            status="active",
            last_event_type="run_summary",
        ),
    )

    assert status == "completed"


def test_resolve_effective_status_keeps_running_when_not_terminal() -> None:
    status = _resolve_effective_status(
        progress_status="running",
        percent=55,
        run_status=_StubRunStatus(
            status="active",
            last_event_type="model_requested",
        ),
    )

    assert status == "running"


def test_resolve_effective_status_marks_failure_when_reason_present() -> None:
    status = _resolve_effective_status(
        progress_status="running",
        percent=0,
        run_status=_StubRunStatus(
            status="active",
            last_event_type="run_summary",
            failure_reason="model timeout",
        ),
    )

    assert status == "failed"


def test_resolve_effective_status_marks_paused_when_blocked() -> None:
    status = _resolve_effective_status(
        progress_status="running",
        percent=0,
        run_status=_StubRunStatus(
            status="blocked",
            last_event_type="run_started",
            blocked_on="approval",
        ),
    )

    assert status == "paused"


def test_resolve_effective_status_marks_model_terminal_timeout_as_failed() -> None:
    status = _resolve_effective_status(
        progress_status="running",
        percent=42,
        run_status=_StubRunStatus(
            status="active",
            last_event_type="model_terminal",
            last_event_outcome="timeout",
        ),
    )

    assert status == "failed"


def test_resolve_effective_status_marks_model_terminal_completed_as_completed() -> None:
    status = _resolve_effective_status(
        progress_status="running",
        percent=0,
        run_status=_StubRunStatus(
            status="active",
            last_event_type="model_terminal",
            last_event_outcome="completed",
        ),
    )

    assert status == "completed"
