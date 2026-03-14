"""Unit tests for shared graph-service startup configuration."""

from __future__ import annotations

import pytest

from src.graph.core.service_config import get_graph_service_settings


def test_graph_service_settings_require_graph_database_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GRAPH_DATABASE_URL", raising=False)

    with pytest.raises(
        RuntimeError,
        match="GRAPH_DATABASE_URL is required for the standalone graph service runtime",
    ):
        get_graph_service_settings()


def test_graph_service_settings_read_service_local_runtime_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GRAPH_DOMAIN_PACK", "biomedical")
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

    settings = get_graph_service_settings()

    assert settings.database_url == "sqlite:///graph-service-test.db"
    assert settings.database_schema == "graph_runtime"
    assert settings.app_name == "Graph Service Test"
    assert settings.host == "127.0.0.1"
    assert settings.port == 9010
    assert settings.reload is True
    assert settings.jwt_secret == "test-jwt-secret-0123456789abcdefghijklmnopqrstuvwxyz"


def test_graph_service_settings_default_identity_comes_from_domain_pack(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GRAPH_DOMAIN_PACK", "biomedical")
    monkeypatch.setenv("GRAPH_DATABASE_URL", "sqlite:///graph-service-test.db")
    monkeypatch.delenv("GRAPH_SERVICE_NAME", raising=False)
    monkeypatch.delenv("GRAPH_JWT_ISSUER", raising=False)

    settings = get_graph_service_settings()

    assert settings.app_name == "Biomedical Graph Service"
    assert settings.jwt_issuer == "graph-biomedical"


def test_graph_service_settings_support_sports_runtime_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GRAPH_DOMAIN_PACK", "sports")
    monkeypatch.setenv("GRAPH_DATABASE_URL", "sqlite:///graph-service-test.db")
    monkeypatch.delenv("GRAPH_SERVICE_NAME", raising=False)
    monkeypatch.delenv("GRAPH_JWT_ISSUER", raising=False)

    settings = get_graph_service_settings()

    assert settings.app_name == "Sports Graph Service"
    assert settings.jwt_issuer == "graph-sports"


def test_graph_service_settings_ignore_legacy_jwt_secret_alias(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GRAPH_DOMAIN_PACK", "biomedical")
    monkeypatch.setenv("GRAPH_DATABASE_URL", "sqlite:///graph-service-test.db")
    monkeypatch.delenv("GRAPH_JWT_SECRET", raising=False)
    monkeypatch.setenv(
        "MED13_DEV_JWT_SECRET",
        "legacy-graph-jwt-secret-0123456789abcdefghijklmnopqrstuvwxyz",
    )

    settings = get_graph_service_settings()

    assert (
        settings.jwt_secret
        != "legacy-graph-jwt-secret-0123456789abcdefghijklmnopqrstuvwxyz"
    )


def test_graph_service_settings_ignore_legacy_test_auth_header_aliases(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GRAPH_DOMAIN_PACK", "biomedical")
    monkeypatch.setenv("GRAPH_DATABASE_URL", "sqlite:///graph-service-test.db")
    monkeypatch.delenv("TESTING", raising=False)
    monkeypatch.delenv("GRAPH_ALLOW_TEST_AUTH_HEADERS", raising=False)
    monkeypatch.setenv("MED13_BYPASS_TEST_AUTH_HEADERS", "1")

    settings = get_graph_service_settings()

    assert settings.allow_test_auth_headers is False
