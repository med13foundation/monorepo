"""Runtime helpers for authenticated graph-service calls from the platform app."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING
from uuid import UUID

from src.domain.entities.user import User, UserRole
from src.infrastructure.security.jwt_provider import JWTProvider

if TYPE_CHECKING:
    from .client import GraphServiceClient

_DEFAULT_GRAPH_SERVICE_URL = "http://127.0.0.1:8090"
_LOCAL_GRAPH_ENVS = frozenset({"development", "local", "test"})
_DEFAULT_GRAPH_JWT_SECRET = (
    "med13-resource-library-dev-jwt-secret-for-development-2026-01"
)
_DEFAULT_GRAPH_SERVICE_USER_ID = UUID("00000000-0000-0000-0000-000000000001")


def _resolve_graph_jwt_secret() -> str:
    graph_secret = os.getenv("GRAPH_JWT_SECRET")
    if isinstance(graph_secret, str) and graph_secret:
        return graph_secret
    return os.getenv("MED13_DEV_JWT_SECRET", _DEFAULT_GRAPH_JWT_SECRET)


def _allow_local_graph_service_fallback() -> bool:
    if os.getenv("TESTING") == "true":
        return True
    environment = os.getenv("MED13_ENV", "development").strip().lower()
    return environment in _LOCAL_GRAPH_ENVS


def resolve_graph_service_url() -> str:
    """Resolve the standalone graph-service base URL."""
    explicit_url = os.getenv("GRAPH_SERVICE_URL")
    if explicit_url is not None and explicit_url.strip():
        return explicit_url.strip().rstrip("/")
    if _allow_local_graph_service_fallback():
        return _DEFAULT_GRAPH_SERVICE_URL
    raise RuntimeError(
        "GRAPH_SERVICE_URL is required outside local development for platform-to-graph calls",
    )


def build_graph_service_bearer_token_for_user(
    user: User,
    *,
    graph_admin: bool = False,
) -> str:
    """Mint one graph-service bearer token for the supplied user."""
    provider = JWTProvider(secret_key=_resolve_graph_jwt_secret())
    return provider.create_access_token(
        user.id,
        user.role.value,
        extra_claims={"graph_admin": graph_admin},
    )


def build_graph_service_bearer_token_for_service(
    *,
    role: UserRole = UserRole.VIEWER,
    graph_admin: bool = True,
) -> str:
    """Mint one graph-service bearer token for backend service-to-service calls."""
    user_id_value = os.getenv("GRAPH_SERVICE_SERVICE_USER_ID")
    service_user_id = (
        UUID(user_id_value)
        if isinstance(user_id_value, str) and user_id_value.strip()
        else _DEFAULT_GRAPH_SERVICE_USER_ID
    )
    provider = JWTProvider(secret_key=_resolve_graph_jwt_secret())
    return provider.create_access_token(
        service_user_id,
        role.value,
        extra_claims={"graph_admin": graph_admin},
    )


def build_graph_service_client_for_user(
    user: User,
    *,
    graph_admin: bool = False,
) -> GraphServiceClient:
    """Build one typed graph-service client authenticated as the supplied user."""
    from .client import GraphServiceClient, GraphServiceClientConfig

    return GraphServiceClient(
        GraphServiceClientConfig(
            base_url=resolve_graph_service_url(),
            default_headers={
                "Authorization": (
                    "Bearer "
                    + build_graph_service_bearer_token_for_user(
                        user,
                        graph_admin=graph_admin,
                    )
                ),
            },
        ),
    )


def build_graph_service_client_for_service(
    *,
    role: UserRole = UserRole.VIEWER,
    graph_admin: bool = True,
) -> GraphServiceClient:
    """Build one typed graph-service client for backend service-to-service calls."""
    from .client import GraphServiceClient, GraphServiceClientConfig

    return GraphServiceClient(
        GraphServiceClientConfig(
            base_url=resolve_graph_service_url(),
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
    "build_graph_service_bearer_token_for_service",
    "build_graph_service_bearer_token_for_user",
    "build_graph_service_client_for_service",
    "build_graph_service_client_for_user",
    "resolve_graph_service_url",
]
