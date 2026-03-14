"""Unit tests for shared graph runtime env resolution."""

from __future__ import annotations

import pytest

from src.graph.core.runtime_env import (
    DEFAULT_GRAPH_JWT_SECRET,
    allow_graph_test_auth_headers,
    resolve_graph_jwt_secret,
)


def test_resolve_graph_jwt_secret_prefers_graph_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GRAPH_JWT_SECRET", "graph-secret")
    monkeypatch.setenv("MED13_DEV_JWT_SECRET", "legacy-secret")

    assert resolve_graph_jwt_secret() == "graph-secret"


def test_resolve_graph_jwt_secret_ignores_legacy_alias(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GRAPH_JWT_SECRET", raising=False)
    monkeypatch.setenv("MED13_DEV_JWT_SECRET", "legacy-secret")

    assert resolve_graph_jwt_secret() == DEFAULT_GRAPH_JWT_SECRET


def test_resolve_graph_jwt_secret_falls_back_to_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GRAPH_JWT_SECRET", raising=False)
    monkeypatch.delenv("MED13_DEV_JWT_SECRET", raising=False)

    assert resolve_graph_jwt_secret() == DEFAULT_GRAPH_JWT_SECRET


def test_allow_graph_test_auth_headers_uses_testing_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TESTING", "true")
    monkeypatch.delenv("GRAPH_ALLOW_TEST_AUTH_HEADERS", raising=False)
    monkeypatch.delenv("MED13_BYPASS_TEST_AUTH_HEADERS", raising=False)

    assert allow_graph_test_auth_headers() is True


def test_allow_graph_test_auth_headers_uses_graph_env_first(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("TESTING", raising=False)
    monkeypatch.setenv("GRAPH_ALLOW_TEST_AUTH_HEADERS", "1")
    monkeypatch.setenv("MED13_BYPASS_TEST_AUTH_HEADERS", "0")

    assert allow_graph_test_auth_headers() is True


def test_allow_graph_test_auth_headers_ignores_legacy_alias(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("TESTING", raising=False)
    monkeypatch.delenv("GRAPH_ALLOW_TEST_AUTH_HEADERS", raising=False)
    monkeypatch.setenv("MED13_BYPASS_TEST_AUTH_HEADERS", "1")

    assert allow_graph_test_auth_headers() is False
