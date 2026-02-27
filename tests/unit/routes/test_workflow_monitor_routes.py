"""Unit tests for workflow monitor route dependency helpers."""

from __future__ import annotations

from src.routes.research_spaces import workflow_monitor_routes as routes


class _StubPort:
    pass


def test_get_run_progress_port_retries_after_backoff(monkeypatch) -> None:
    routes._reset_run_progress_port_cache_for_tests()

    calls = {"count": 0}
    expected_port = _StubPort()

    def _build_port() -> _StubPort:
        calls["count"] += 1
        if calls["count"] == 1:
            msg = "transient startup failure"
            raise RuntimeError(msg)
        return expected_port

    monotonic_values = iter((100.0, 110.0, 131.0, 132.0))

    monkeypatch.setattr(routes, "_build_run_progress_port", _build_port)
    monkeypatch.setattr(routes, "monotonic", lambda: next(monotonic_values))

    first = routes.get_run_progress_port()
    second = routes.get_run_progress_port()
    third = routes.get_run_progress_port()
    fourth = routes.get_run_progress_port()

    assert first is None
    assert second is None
    assert third is expected_port
    assert fourth is expected_port
    assert calls["count"] == 2

    routes._reset_run_progress_port_cache_for_tests()
