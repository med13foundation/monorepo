"""Shared dependency helpers for Artana observability routes."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from threading import Lock
from time import monotonic

from src.application.services.ports.artana_run_trace_port import ArtanaRunTracePort
from src.infrastructure.llm.state.artana_run_trace_repository import (
    ArtanaKernelRunTraceRepository,
)

logger = logging.getLogger(__name__)
_RUN_TRACE_RETRY_INTERVAL_SECONDS = 30.0
_RUN_TRACE_CACHE_LOCK = Lock()


@dataclass
class _RunTracePortState:
    port: ArtanaRunTracePort | None = None
    last_failure_monotonic: float | None = None


_RUN_TRACE_STATE = _RunTracePortState()


def _build_run_trace_port() -> ArtanaRunTracePort:
    return ArtanaKernelRunTraceRepository()


def reset_artana_run_trace_port_cache_for_tests() -> None:
    """Reset cached port state for deterministic tests."""
    with _RUN_TRACE_CACHE_LOCK:
        _RUN_TRACE_STATE.port = None
        _RUN_TRACE_STATE.last_failure_monotonic = None


def get_artana_run_trace_port() -> ArtanaRunTracePort | None:
    """Provide an optional shared Artana trace-reader adapter."""
    with _RUN_TRACE_CACHE_LOCK:
        if _RUN_TRACE_STATE.port is not None:
            return _RUN_TRACE_STATE.port

        now_monotonic = monotonic()
        if _RUN_TRACE_STATE.last_failure_monotonic is not None and (
            now_monotonic - _RUN_TRACE_STATE.last_failure_monotonic
            < _RUN_TRACE_RETRY_INTERVAL_SECONDS
        ):
            return None

        try:
            port = _build_run_trace_port()
        except Exception as exc:  # pragma: no cover - optional enrichment
            _RUN_TRACE_STATE.last_failure_monotonic = now_monotonic
            logger.warning(
                "Artana run-trace reader unavailable; observability detail is partial. %s",
                exc,
            )
            return None

        _RUN_TRACE_STATE.port = port
        _RUN_TRACE_STATE.last_failure_monotonic = None
        return port


__all__ = [
    "get_artana_run_trace_port",
    "reset_artana_run_trace_port_cache_for_tests",
]
