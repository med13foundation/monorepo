from __future__ import annotations

import pytest

from services.graph_api.config import GraphServiceSettings, get_settings


def test_graph_service_config_wrapper_require_graph_database_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GRAPH_DATABASE_URL", raising=False)

    with pytest.raises(
        RuntimeError,
        match="GRAPH_DATABASE_URL is required for the standalone graph service runtime",
    ):
        get_settings()


def test_graph_service_config_wrapper_returns_graph_service_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GRAPH_DATABASE_URL", "sqlite:///graph-service-test.db")

    settings = get_settings()

    assert isinstance(settings, GraphServiceSettings)
