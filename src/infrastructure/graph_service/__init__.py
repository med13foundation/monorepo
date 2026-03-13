"""Lazy exports for the standalone graph-service client package."""

from __future__ import annotations

__all__ = [
    "GraphServiceClient",
    "GraphServiceClientConfig",
    "GraphServiceClientError",
    "GraphServiceGraphSearchAdapter",
    "GraphServiceHealthResponse",
    "GraphServiceSpaceLifecycleSync",
    "build_graph_connection_seed_runner_for_service",
    "build_graph_connection_seed_runner_for_user",
    "build_graph_search_service_for_user",
    "build_graph_search_service_for_service",
    "build_graph_service_bearer_token_for_service",
    "build_graph_service_bearer_token_for_user",
    "build_graph_service_client_for_service",
    "build_graph_service_client_for_user",
    "resolve_graph_service_url",
]


def __getattr__(name: str) -> object:
    if name in {
        "GraphServiceClient",
        "GraphServiceClientConfig",
        "GraphServiceClientError",
        "GraphServiceHealthResponse",
    }:
        from .client import (
            GraphServiceClient,
            GraphServiceClientConfig,
            GraphServiceClientError,
            GraphServiceHealthResponse,
        )

        return {
            "GraphServiceClient": GraphServiceClient,
            "GraphServiceClientConfig": GraphServiceClientConfig,
            "GraphServiceClientError": GraphServiceClientError,
            "GraphServiceHealthResponse": GraphServiceHealthResponse,
        }[name]

    if name == "GraphServiceSpaceLifecycleSync":
        from .space_lifecycle_sync import GraphServiceSpaceLifecycleSync

        return GraphServiceSpaceLifecycleSync

    if name == "build_graph_connection_seed_runner_for_user":
        from .pipeline import build_graph_connection_seed_runner_for_user

        return build_graph_connection_seed_runner_for_user

    if name in {
        "GraphServiceGraphSearchAdapter",
        "build_graph_connection_seed_runner_for_service",
        "build_graph_search_service_for_user",
        "build_graph_search_service_for_service",
    }:
        from .pipeline import (
            GraphServiceGraphSearchAdapter,
            build_graph_connection_seed_runner_for_service,
            build_graph_search_service_for_service,
            build_graph_search_service_for_user,
        )

        return {
            "GraphServiceGraphSearchAdapter": GraphServiceGraphSearchAdapter,
            "build_graph_connection_seed_runner_for_service": (
                build_graph_connection_seed_runner_for_service
            ),
            "build_graph_search_service_for_user": (
                build_graph_search_service_for_user
            ),
            "build_graph_search_service_for_service": (
                build_graph_search_service_for_service
            ),
        }[name]

    if name in {
        "build_graph_service_bearer_token_for_service",
        "build_graph_service_bearer_token_for_user",
        "build_graph_service_client_for_service",
        "build_graph_service_client_for_user",
        "resolve_graph_service_url",
    }:
        from .runtime import (
            build_graph_service_bearer_token_for_service,
            build_graph_service_bearer_token_for_user,
            build_graph_service_client_for_service,
            build_graph_service_client_for_user,
            resolve_graph_service_url,
        )

        return {
            "build_graph_service_bearer_token_for_service": (
                build_graph_service_bearer_token_for_service
            ),
            "build_graph_service_bearer_token_for_user": (
                build_graph_service_bearer_token_for_user
            ),
            "build_graph_service_client_for_service": (
                build_graph_service_client_for_service
            ),
            "build_graph_service_client_for_user": (
                build_graph_service_client_for_user
            ),
            "resolve_graph_service_url": resolve_graph_service_url,
        }[name]

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
