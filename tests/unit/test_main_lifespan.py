from __future__ import annotations

import pytest

from src import main


class _RecordingSession:
    def __init__(self) -> None:
        self.committed = False
        self.rolled_back = False
        self.closed = False

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True

    def close(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_lifespan_closes_startup_session_before_serving(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _RecordingSession()
    events: list[str] = []

    async def _noop_task(*_args: object, **_kwargs: object) -> None:
        return None

    monkeypatch.setattr(main, "_skip_startup_tasks", lambda: False)
    monkeypatch.setattr(main, "_scheduler_disabled", lambda: True)
    monkeypatch.setattr(main, "SessionLocal", lambda: session)
    monkeypatch.setattr(
        main,
        "set_session_rls_context",
        lambda *_args, **_kwargs: events.append("rls"),
    )
    monkeypatch.setattr(
        main,
        "initialize_legacy_session",
        lambda _session: events.append("init"),
    )
    monkeypatch.setattr(
        main,
        "ensure_source_catalog_seeded",
        lambda _session: events.append("catalog"),
    )
    monkeypatch.setattr(
        main,
        "ensure_default_research_space_seeded",
        lambda _session: events.append("space"),
    )
    monkeypatch.setattr(
        main,
        "ensure_system_status_initialized",
        lambda _session: events.append("status"),
    )
    monkeypatch.setattr(main, "run_session_cleanup_loop", _noop_task)

    class _DummyEngine:
        async def dispose(self) -> None:
            events.append("dispose")

    monkeypatch.setattr(main.container, "engine", _DummyEngine())

    async with main.lifespan(main.create_app()):
        assert session.committed is True
        assert session.closed is True
        assert session.rolled_back is False

    assert events[:5] == ["rls", "init", "catalog", "space", "status"]
    assert events[-1] == "dispose"
