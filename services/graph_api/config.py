"""Compatibility wrapper for graph-service startup configuration."""

from __future__ import annotations

from src.graph.core.service_config import (
    GraphServiceSettings,
    _require_env,
    get_graph_service_settings,
)


def get_settings() -> GraphServiceSettings:
    """Resolve graph service settings through graph-core runtime config."""
    return get_graph_service_settings()


__all__ = ["GraphServiceSettings", "_require_env", "get_settings"]
