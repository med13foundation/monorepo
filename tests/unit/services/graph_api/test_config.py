from __future__ import annotations

import pytest

from services.graph_api.config import get_settings


def test_graph_service_settings_require_graph_database_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GRAPH_DATABASE_URL", raising=False)

    with pytest.raises(
        RuntimeError,
        match="GRAPH_DATABASE_URL is required for the standalone graph service runtime",
    ):
        get_settings()


def test_graph_service_settings_read_service_local_runtime_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GRAPH_DATABASE_URL", "sqlite:///graph-service-test.db")
    monkeypatch.setenv("GRAPH_DB_SCHEMA", "graph_runtime")
    monkeypatch.setenv("GRAPH_SERVICE_NAME", "Graph Service Test")
    monkeypatch.setenv("GRAPH_SERVICE_HOST", "127.0.0.1")
    monkeypatch.setenv("GRAPH_SERVICE_PORT", "9010")
    monkeypatch.setenv("GRAPH_SERVICE_RELOAD", "1")
    monkeypatch.setenv(
        "GRAPH_JWT_SECRET",
        "test-jwt-secret-0123456789abcdefghijklmnopqrstuvwxyz",
    )

    settings = get_settings()

    assert settings.database_url == "sqlite:///graph-service-test.db"
    assert settings.database_schema == "graph_runtime"
    assert settings.app_name == "Graph Service Test"
    assert settings.host == "127.0.0.1"
    assert settings.port == 9010
    assert settings.reload is True
