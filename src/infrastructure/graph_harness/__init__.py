"""Lazy exports for graph-harness platform clients."""

from __future__ import annotations

__all__ = [
    "GraphHarnessClient",
    "GraphHarnessClientConfig",
    "GraphHarnessClientError",
    "GraphHarnessGraphSearchAdapter",
    "build_graph_connection_seed_runner_for_service",
    "build_graph_connection_seed_runner_for_user",
    "build_graph_harness_client_for_service",
    "build_graph_harness_client_for_user",
    "build_graph_search_service_for_service",
    "build_graph_search_service_for_user",
    "resolve_graph_harness_service_url",
]


def __getattr__(name: str) -> object:
    if name in {
        "GraphHarnessClient",
        "GraphHarnessClientConfig",
        "GraphHarnessClientError",
    }:
        from .client import (
            GraphHarnessClient,
            GraphHarnessClientConfig,
            GraphHarnessClientError,
        )

        return {
            "GraphHarnessClient": GraphHarnessClient,
            "GraphHarnessClientConfig": GraphHarnessClientConfig,
            "GraphHarnessClientError": GraphHarnessClientError,
        }[name]

    if name in {
        "GraphHarnessGraphSearchAdapter",
        "build_graph_connection_seed_runner_for_service",
        "build_graph_connection_seed_runner_for_user",
        "build_graph_search_service_for_service",
        "build_graph_search_service_for_user",
    }:
        from .pipeline import (
            GraphHarnessGraphSearchAdapter,
            build_graph_connection_seed_runner_for_service,
            build_graph_connection_seed_runner_for_user,
            build_graph_search_service_for_service,
            build_graph_search_service_for_user,
        )

        return {
            "GraphHarnessGraphSearchAdapter": GraphHarnessGraphSearchAdapter,
            "build_graph_connection_seed_runner_for_service": (
                build_graph_connection_seed_runner_for_service
            ),
            "build_graph_connection_seed_runner_for_user": (
                build_graph_connection_seed_runner_for_user
            ),
            "build_graph_search_service_for_service": (
                build_graph_search_service_for_service
            ),
            "build_graph_search_service_for_user": build_graph_search_service_for_user,
        }[name]

    if name in {
        "build_graph_harness_client_for_service",
        "build_graph_harness_client_for_user",
        "resolve_graph_harness_service_url",
    }:
        from .runtime import (
            build_graph_harness_client_for_service,
            build_graph_harness_client_for_user,
            resolve_graph_harness_service_url,
        )

        return {
            "build_graph_harness_client_for_service": (
                build_graph_harness_client_for_service
            ),
            "build_graph_harness_client_for_user": build_graph_harness_client_for_user,
            "resolve_graph_harness_service_url": resolve_graph_harness_service_url,
        }[name]

    raise AttributeError(name)
