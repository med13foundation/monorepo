"""Shared graph env resolution for relation auto-promotion policy."""

from __future__ import annotations

import os

_ENV_ENABLED = ("GRAPH_RELATION_AUTOPROMOTE_ENABLED",)
_ENV_MIN_DISTINCT_SOURCES = ("GRAPH_RELATION_AUTOPROMOTE_MIN_DISTINCT_SOURCES",)
_ENV_MIN_AGGREGATE_CONFIDENCE = ("GRAPH_RELATION_AUTOPROMOTE_MIN_AGGREGATE_CONFIDENCE",)
_ENV_REQUIRE_DISTINCT_DOCUMENTS = (
    "GRAPH_RELATION_AUTOPROMOTE_REQUIRE_DISTINCT_DOCUMENTS",
)
_ENV_REQUIRE_DISTINCT_RUNS = ("GRAPH_RELATION_AUTOPROMOTE_REQUIRE_DISTINCT_RUNS",)
_ENV_BLOCK_CONFLICTING_EVIDENCE = (
    "GRAPH_RELATION_AUTOPROMOTE_BLOCK_CONFLICTING_EVIDENCE",
)
_ENV_MIN_EVIDENCE_TIER = ("GRAPH_RELATION_AUTOPROMOTE_MIN_EVIDENCE_TIER",)
_ENV_COMPUTATIONAL_MIN_DISTINCT_SOURCES = (
    "GRAPH_RELATION_AUTOPROMOTE_COMPUTATIONAL_MIN_DISTINCT_SOURCES",
)
_ENV_COMPUTATIONAL_MIN_AGGREGATE_CONFIDENCE = (
    "GRAPH_RELATION_AUTOPROMOTE_COMPUTATIONAL_MIN_AGGREGATE_CONFIDENCE",
)
_ENV_CONFLICTING_CONFIDENCE_THRESHOLD = (
    "GRAPH_RELATION_AUTOPROMOTE_CONFLICTING_CONFIDENCE_THRESHOLD",
)


def _read_first_env(names: tuple[str, ...]) -> str | None:
    for name in names:
        raw = os.getenv(name)
        if raw is not None:
            return raw
    return None


def read_graph_relation_autopromote_bool(
    names: tuple[str, ...],
    *,
    default: bool,
) -> bool:
    raw = _read_first_env(names)
    if raw is None:
        return default
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


def read_graph_relation_autopromote_int(
    names: tuple[str, ...],
    default: int,
    *,
    minimum: int = 0,
) -> int:
    raw = _read_first_env(names)
    if raw is None:
        return default
    try:
        parsed = int(raw)
    except ValueError:
        return default
    return max(parsed, minimum)


def read_graph_relation_autopromote_float(
    names: tuple[str, ...],
    default: float,
    *,
    minimum: float = 0.0,
    maximum: float = 1.0,
) -> float:
    raw = _read_first_env(names)
    if raw is None:
        return default
    try:
        parsed = float(raw)
    except ValueError:
        return default
    if parsed < minimum:
        return minimum
    if parsed > maximum:
        return maximum
    return parsed


def read_graph_relation_autopromote_tier(default: str) -> str:
    raw = _read_first_env(_ENV_MIN_EVIDENCE_TIER)
    if raw is None:
        return default
    normalized = raw.strip().upper()
    return normalized or default


__all__ = [
    "_ENV_BLOCK_CONFLICTING_EVIDENCE",
    "_ENV_COMPUTATIONAL_MIN_AGGREGATE_CONFIDENCE",
    "_ENV_COMPUTATIONAL_MIN_DISTINCT_SOURCES",
    "_ENV_CONFLICTING_CONFIDENCE_THRESHOLD",
    "_ENV_ENABLED",
    "_ENV_MIN_AGGREGATE_CONFIDENCE",
    "_ENV_MIN_DISTINCT_SOURCES",
    "_ENV_MIN_EVIDENCE_TIER",
    "_ENV_REQUIRE_DISTINCT_DOCUMENTS",
    "_ENV_REQUIRE_DISTINCT_RUNS",
    "read_graph_relation_autopromote_bool",
    "read_graph_relation_autopromote_float",
    "read_graph_relation_autopromote_int",
    "read_graph_relation_autopromote_tier",
]
