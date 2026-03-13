"""Configuration for the standalone graph API service."""

from __future__ import annotations

import os
from dataclasses import dataclass

from src.database.graph_schema import resolve_graph_db_schema

_DEFAULT_JWT_SECRET = "med13-resource-library-dev-jwt-secret-for-development-2026-01"  # noqa: S105 - development-only fallback for local/runtime tooling


@dataclass(frozen=True)
class GraphServiceSettings:
    """Configuration values used by the graph service runtime."""

    app_name: str
    database_url: str
    database_schema: str
    host: str
    port: int
    reload: bool
    jwt_secret: str
    jwt_algorithm: str
    jwt_issuer: str
    allow_test_auth_headers: bool


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if value is None or not value.strip():
        message = f"{name} is required for the standalone graph service runtime"
        raise RuntimeError(message)
    return value.strip()


def _bool_env(name: str, *, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def get_settings() -> GraphServiceSettings:
    """Resolve graph service settings from environment variables."""
    database_url = _require_env("GRAPH_DATABASE_URL")
    jwt_secret = (
        os.getenv("GRAPH_JWT_SECRET")
        or os.getenv("MED13_DEV_JWT_SECRET")
        or _DEFAULT_JWT_SECRET
    )
    return GraphServiceSettings(
        app_name=os.getenv("GRAPH_SERVICE_NAME", "MED13 Graph Service"),
        database_url=database_url,
        database_schema=resolve_graph_db_schema(),
        host=os.getenv("GRAPH_SERVICE_HOST", "0.0.0.0"),  # noqa: S104
        port=int(os.getenv("GRAPH_SERVICE_PORT", "8090")),
        reload=_bool_env("GRAPH_SERVICE_RELOAD", default=False),
        jwt_secret=jwt_secret,
        jwt_algorithm=os.getenv("GRAPH_JWT_ALGORITHM", "HS256"),
        jwt_issuer=os.getenv("GRAPH_JWT_ISSUER", "med13-resource-library"),
        allow_test_auth_headers=(
            os.getenv("TESTING") == "true"
            or os.getenv("GRAPH_ALLOW_TEST_AUTH_HEADERS") == "1"
            or os.getenv("MED13_BYPASS_TEST_AUTH_HEADERS") == "1"
        ),
    )


__all__ = ["GraphServiceSettings", "get_settings"]
