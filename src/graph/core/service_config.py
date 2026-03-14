"""Shared graph-service startup configuration for the standalone runtime."""

from __future__ import annotations

import os
from dataclasses import dataclass

from src.database.graph_schema import resolve_graph_db_schema
from src.graph.core.runtime_env import (
    allow_graph_test_auth_headers,
    resolve_graph_jwt_secret,
)
from src.graph.runtime import create_graph_domain_pack


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


def get_graph_service_settings() -> GraphServiceSettings:
    """Resolve graph service settings from environment variables."""
    database_url = _require_env("GRAPH_DATABASE_URL")
    graph_domain_pack = create_graph_domain_pack()
    return GraphServiceSettings(
        app_name=os.getenv(
            "GRAPH_SERVICE_NAME",
            graph_domain_pack.runtime_identity.service_name,
        ),
        database_url=database_url,
        database_schema=resolve_graph_db_schema(),
        host=os.getenv("GRAPH_SERVICE_HOST", "0.0.0.0"),  # noqa: S104
        port=int(os.getenv("GRAPH_SERVICE_PORT", "8090")),
        reload=_bool_env("GRAPH_SERVICE_RELOAD", default=False),
        jwt_secret=resolve_graph_jwt_secret(),
        jwt_algorithm=os.getenv("GRAPH_JWT_ALGORITHM", "HS256"),
        jwt_issuer=os.getenv(
            "GRAPH_JWT_ISSUER",
            graph_domain_pack.runtime_identity.jwt_issuer,
        ),
        allow_test_auth_headers=allow_graph_test_auth_headers(),
    )
