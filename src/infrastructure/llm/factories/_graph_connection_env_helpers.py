"""Environment configuration helpers for graph-connection agent factory."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.domain.agents.models import ModelSpec


def read_positive_int_from_env(*, name: str, default: int) -> int:
    """Parse a positive integer environment variable with fallback."""
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    normalized = raw_value.strip()
    if not normalized:
        return default
    if normalized.isdigit():
        parsed = int(normalized)
        return parsed if parsed > 0 else default
    return default


def resolve_graph_connection_usage_limits(  # noqa: PLR0913
    *,
    request_limit_default: int,
    tool_calls_limit_default: int,
    request_limit_env: str,
    tool_calls_limit_env: str,
) -> tuple[int, int]:
    """Resolve request/tool-call limits for graph connection agent runs."""
    request_limit = read_positive_int_from_env(
        name=request_limit_env,
        default=request_limit_default,
    )
    tool_calls_limit = read_positive_int_from_env(
        name=tool_calls_limit_env,
        default=tool_calls_limit_default,
    )
    return request_limit, tool_calls_limit


def resolve_graph_connection_timeout_seconds(
    *,
    model_spec: ModelSpec,
    timeout_env: str,
) -> int:
    """Resolve graph connection timeout with model-spec and env fallback."""
    default_timeout = int(model_spec.timeout_seconds)
    if default_timeout <= 0:
        default_timeout = 30
    return read_positive_int_from_env(
        name=timeout_env,
        default=default_timeout,
    )


def resolve_graph_connection_max_retries(
    *,
    model_spec: ModelSpec,
    fallback: int,
    retries_env: str,
) -> int:
    """Resolve graph connection retry count with env override support."""
    default_value = model_spec.max_retries if model_spec.max_retries > 0 else fallback
    return read_positive_int_from_env(
        name=retries_env,
        default=default_value if default_value > 0 else 1,
    )


__all__ = [
    "read_positive_int_from_env",
    "resolve_graph_connection_max_retries",
    "resolve_graph_connection_timeout_seconds",
    "resolve_graph_connection_usage_limits",
]
