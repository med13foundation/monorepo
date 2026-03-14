"""Service-local startup configuration for the harness API."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

_DEFAULT_HOST = "0.0.0.0"  # noqa: S104


@dataclass(frozen=True, slots=True)
class GraphHarnessServiceSettings:
    """Resolved runtime settings for the harness API service."""

    app_name: str
    host: str
    port: int
    reload: bool
    openapi_url: str
    version: str
    graph_api_url: str
    graph_api_timeout_seconds: float
    scheduler_poll_seconds: float
    scheduler_run_once: bool
    worker_id: str
    worker_poll_seconds: float
    worker_run_once: bool
    worker_lease_ttl_seconds: int


def _read_bool_env(name: str, *, default: bool) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    normalized = raw_value.strip().lower()
    return normalized in {"1", "true", "yes", "on"}


@lru_cache(maxsize=1)
def get_settings() -> GraphHarnessServiceSettings:
    """Return cached harness service settings."""
    raw_port = os.getenv("GRAPH_HARNESS_SERVICE_PORT", "8091").strip()
    return GraphHarnessServiceSettings(
        app_name=os.getenv(
            "GRAPH_HARNESS_APP_NAME",
            "MED13 Graph Harness API",
        ).strip()
        or "MED13 Graph Harness API",
        host=os.getenv("GRAPH_HARNESS_SERVICE_HOST", _DEFAULT_HOST).strip()
        or _DEFAULT_HOST,
        port=int(raw_port),
        reload=_read_bool_env("GRAPH_HARNESS_SERVICE_RELOAD", default=False),
        openapi_url="/openapi.json",
        version="0.1.0",
        graph_api_url=os.getenv(
            "GRAPH_API_URL",
            "http://127.0.0.1:8080",
        ).strip()
        or "http://127.0.0.1:8080",
        graph_api_timeout_seconds=float(
            os.getenv("GRAPH_HARNESS_GRAPH_API_TIMEOUT_SECONDS", "10.0").strip(),
        ),
        scheduler_poll_seconds=float(
            os.getenv("GRAPH_HARNESS_SCHEDULER_POLL_SECONDS", "300").strip(),
        ),
        scheduler_run_once=_read_bool_env(
            "GRAPH_HARNESS_SCHEDULER_RUN_ONCE",
            default=False,
        ),
        worker_id=os.getenv(
            "GRAPH_HARNESS_WORKER_ID",
            "graph-harness-worker",
        ).strip()
        or "graph-harness-worker",
        worker_poll_seconds=float(
            os.getenv("GRAPH_HARNESS_WORKER_POLL_SECONDS", "30").strip(),
        ),
        worker_run_once=_read_bool_env(
            "GRAPH_HARNESS_WORKER_RUN_ONCE",
            default=False,
        ),
        worker_lease_ttl_seconds=int(
            os.getenv("GRAPH_HARNESS_WORKER_LEASE_TTL_SECONDS", "300").strip(),
        ),
    )


__all__ = ["GraphHarnessServiceSettings", "get_settings"]
