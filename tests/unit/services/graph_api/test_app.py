"""Unit tests for standalone graph-service app startup."""

from __future__ import annotations

from types import SimpleNamespace

from services.graph_api import app as graph_app_module
from src.graph.product_contract import GRAPH_OPENAPI_URL, GRAPH_SERVICE_VERSION


def test_create_app_bootstraps_default_graph_domain_packs(
    monkeypatch,
) -> None:
    bootstrap_calls: list[None] = []

    monkeypatch.setattr(
        graph_app_module,
        "bootstrap_default_graph_domain_packs",
        lambda: bootstrap_calls.append(None),
    )
    monkeypatch.setattr(
        graph_app_module,
        "get_settings",
        lambda: SimpleNamespace(app_name="Graph Service Test"),
    )

    app = graph_app_module.create_app()

    assert app.title == "Graph Service Test"
    assert app.version == GRAPH_SERVICE_VERSION
    assert app.openapi_url == GRAPH_OPENAPI_URL
    assert bootstrap_calls == [None]
