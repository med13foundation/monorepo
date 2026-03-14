"""Runtime helpers for authenticated graph-harness calls from the platform app."""

from __future__ import annotations

import os

from src.domain.entities.user import User, UserRole
from src.infrastructure.graph_service.runtime import (
    build_graph_service_bearer_token_for_service,
    build_graph_service_bearer_token_for_user,
)

from .client import GraphHarnessClient, GraphHarnessClientConfig

_DEFAULT_GRAPH_HARNESS_SERVICE_URL = "http://127.0.0.1:8091"
_LOCAL_GRAPH_HARNESS_ENVS = frozenset({"development", "local", "test"})


class MissingGraphHarnessServiceUrlError(RuntimeError):
    """Raised when the standalone graph-harness URL is required but unset."""

    def __init__(self) -> None:
        super().__init__(
            "GRAPH_HARNESS_SERVICE_URL is required outside local development "
            "for platform-to-harness calls",
        )


def _allow_local_graph_harness_fallback() -> bool:
    if os.getenv("TESTING") == "true":
        return True
    environment = os.getenv("MED13_ENV", "development").strip().lower()
    return environment in _LOCAL_GRAPH_HARNESS_ENVS


def resolve_graph_harness_service_url() -> str:
    """Resolve the standalone graph-harness base URL."""
    explicit_url = os.getenv("GRAPH_HARNESS_SERVICE_URL")
    if explicit_url is not None and explicit_url.strip():
        return explicit_url.strip().rstrip("/")
    if _allow_local_graph_harness_fallback():
        return _DEFAULT_GRAPH_HARNESS_SERVICE_URL
    raise MissingGraphHarnessServiceUrlError


def build_graph_harness_client_for_user(
    user: User,
) -> GraphHarnessClient:
    """Build one typed graph-harness client authenticated as the supplied user."""
    return GraphHarnessClient(
        GraphHarnessClientConfig(
            base_url=resolve_graph_harness_service_url(),
            default_headers={
                "Authorization": (
                    "Bearer " + build_graph_service_bearer_token_for_user(user)
                ),
            },
        ),
    )


def build_graph_harness_client_for_service(
    *,
    role: UserRole = UserRole.VIEWER,
    graph_admin: bool = True,
) -> GraphHarnessClient:
    """Build one typed graph-harness client for backend service-to-service calls."""
    return GraphHarnessClient(
        GraphHarnessClientConfig(
            base_url=resolve_graph_harness_service_url(),
            default_headers={
                "Authorization": (
                    "Bearer "
                    + build_graph_service_bearer_token_for_service(
                        role=role,
                        graph_admin=graph_admin,
                    )
                ),
            },
        ),
    )


__all__ = [
    "build_graph_harness_client_for_service",
    "build_graph_harness_client_for_user",
    "resolve_graph_harness_service_url",
]
