"""Regression tests for graph-intelligence factory delegation."""

from __future__ import annotations

from src.infrastructure.dependency_injection.service_factories import (
    ApplicationServiceFactoryMixin,
)


class _Factory(ApplicationServiceFactoryMixin):
    """Minimal concrete factory for delegation tests."""


def test_create_graph_connection_service_delegates_to_graph_service_composition(
    monkeypatch,
) -> None:
    factory = _Factory()
    session = object()
    expected_service = object()
    captured: dict[str, object] = {}

    def _build(session_arg: object) -> object:
        captured["session"] = session_arg
        return expected_service

    monkeypatch.setattr(
        "src.infrastructure.dependency_injection.service_factories.build_graph_connection_service",
        _build,
    )

    result = factory.create_graph_connection_service(session)

    assert result is expected_service
    assert captured == {"session": session}


def test_create_graph_search_service_delegates_to_graph_service_composition(
    monkeypatch,
) -> None:
    factory = _Factory()
    session = object()
    expected_service = object()
    captured: dict[str, object] = {}

    def _build(session_arg: object) -> object:
        captured["session"] = session_arg
        return expected_service

    monkeypatch.setattr(
        "src.infrastructure.dependency_injection.service_factories.build_graph_search_service",
        _build,
    )

    result = factory.create_graph_search_service(session)

    assert result is expected_service
    assert captured == {"session": session}
