from __future__ import annotations

from pathlib import Path

import pytest

from services.graph_api import manage


def test_connection_kwargs_use_graph_database_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "GRAPH_DATABASE_URL",
        "postgresql+psycopg2://graph_user:graph_pw@graph-db.local:5433/graph_db",
    )

    assert manage._connection_kwargs() == {
        "dbname": "graph_db",
        "user": "graph_user",
        "password": "graph_pw",
        "host": "graph-db.local",
        "port": 5433,
    }


def test_migrate_graph_database_uses_graph_database_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    graph_database_url = (
        "postgresql+psycopg2://graph_user:graph_pw@graph-db.local:5433/graph_db"
    )
    monkeypatch.setenv("GRAPH_DATABASE_URL", graph_database_url)
    monkeypatch.setenv("GRAPH_DB_SCHEMA", "graph_runtime")
    monkeypatch.setattr(manage, "_resolve_alembic_binary", lambda: "/tmp/alembic")

    captured: dict[str, object] = {}

    def _fake_run(
        command: list[str],
        *,
        check: bool,
        cwd: Path,
        env: dict[str, str],
    ) -> None:
        captured["command"] = command
        captured["check"] = check
        captured["cwd"] = cwd
        captured["env"] = env

    monkeypatch.setattr(manage.subprocess, "run", _fake_run)

    manage.migrate_graph_database(revision="heads")

    assert captured["command"] == [
        "/tmp/alembic",
        "-c",
        str(manage._ALEMBIC_CONFIG),
        "upgrade",
        "heads",
    ]
    assert captured["check"] is True
    assert captured["cwd"] == Path(manage._SERVICE_ROOT)
    env = captured["env"]
    assert isinstance(env, dict)
    assert env["ALEMBIC_DATABASE_URL"] == graph_database_url
    assert env["GRAPH_DB_SCHEMA"] == "graph_runtime"
    assert env["ALEMBIC_GRAPH_DB_SCHEMA"] == "graph_runtime"
