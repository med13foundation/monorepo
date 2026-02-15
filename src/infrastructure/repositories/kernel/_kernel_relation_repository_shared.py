"""Shared policy and utility types for kernel relation repositories."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

_DEFAULT_EVIDENCE_TIER = "COMPUTATIONAL"
_EVIDENCE_TIER_RANK: dict[str, int] = {
    "EXPERT_CURATED": 6,
    "CLINICAL": 5,
    "EXPERIMENTAL": 4,
    "LITERATURE": 3,
    "STRUCTURED_DATA": 2,
    "COMPUTATIONAL": 1,
}
_PROMOTABLE_CURATION_STATUSES = {"DRAFT", "UNDER_REVIEW"}
_DEFAULT_MIN_EVIDENCE_TIER = "LITERATURE"
_SPACE_POLICY_SETTINGS_KEY = "relation_auto_promotion"
_SPACE_POLICY_CUSTOM_PREFIX = "relation_autopromote_"


def _read_bool_env(name: str, *, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


def _read_int_env(name: str, default: int, *, minimum: int = 0) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        parsed = int(raw)
    except ValueError:
        return default
    return max(parsed, minimum)


def _read_float_env(
    name: str,
    default: float,
    *,
    minimum: float = 0.0,
    maximum: float = 1.0,
) -> float:
    raw = os.getenv(name)
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


def _parse_bool_setting(value: object, *, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return default


def _parse_int_setting(value: object, *, default: int, minimum: int = 0) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return max(value, minimum)
    if isinstance(value, float):
        return max(int(value), minimum)
    if isinstance(value, str):
        try:
            parsed = int(value.strip())
        except ValueError:
            return default
        return max(parsed, minimum)
    return default


def _parse_float_setting(
    value: object,
    *,
    default: float,
    minimum: float = 0.0,
    maximum: float = 1.0,
) -> float:
    if isinstance(value, bool):
        return default
    if isinstance(value, float | int):
        parsed = float(value)
    elif isinstance(value, str):
        try:
            parsed = float(value.strip())
        except ValueError:
            return default
    else:
        return default
    if parsed < minimum:
        return minimum
    if parsed > maximum:
        return maximum
    return parsed


def _normalize_tier_setting(value: object, *, default: str) -> str:
    if not isinstance(value, str):
        return default
    normalized = value.strip().upper()
    if not normalized:
        return default
    return normalized


@dataclass(frozen=True)
class AutoPromotionPolicy:
    """Policy used to auto-promote canonical relations after evidence updates."""

    enabled: bool = True
    min_distinct_sources: int = 3
    min_aggregate_confidence: float = 0.95
    require_distinct_documents: bool = True
    require_distinct_runs: bool = True
    block_if_conflicting_evidence: bool = True
    min_evidence_tier: str = _DEFAULT_MIN_EVIDENCE_TIER
    computational_min_distinct_sources: int = 5
    computational_min_aggregate_confidence: float = 0.99
    conflicting_confidence_threshold: float = 0.5

    @classmethod
    def from_environment(cls) -> AutoPromotionPolicy:
        """Build relation auto-promotion policy from environment variables."""
        normalized_tier = (
            os.getenv(
                "MED13_RELATION_AUTOPROMOTE_MIN_EVIDENCE_TIER",
                _DEFAULT_MIN_EVIDENCE_TIER,
            )
            .strip()
            .upper()
        )
        if not normalized_tier:
            normalized_tier = _DEFAULT_MIN_EVIDENCE_TIER
        return cls(
            enabled=_read_bool_env(
                "MED13_RELATION_AUTOPROMOTE_ENABLED",
                default=True,
            ),
            min_distinct_sources=_read_int_env(
                "MED13_RELATION_AUTOPROMOTE_MIN_DISTINCT_SOURCES",
                3,
                minimum=1,
            ),
            min_aggregate_confidence=_read_float_env(
                "MED13_RELATION_AUTOPROMOTE_MIN_AGGREGATE_CONFIDENCE",
                0.95,
            ),
            require_distinct_documents=_read_bool_env(
                "MED13_RELATION_AUTOPROMOTE_REQUIRE_DISTINCT_DOCUMENTS",
                default=True,
            ),
            require_distinct_runs=_read_bool_env(
                "MED13_RELATION_AUTOPROMOTE_REQUIRE_DISTINCT_RUNS",
                default=True,
            ),
            block_if_conflicting_evidence=_read_bool_env(
                "MED13_RELATION_AUTOPROMOTE_BLOCK_CONFLICTING_EVIDENCE",
                default=True,
            ),
            min_evidence_tier=normalized_tier,
            computational_min_distinct_sources=_read_int_env(
                "MED13_RELATION_AUTOPROMOTE_COMPUTATIONAL_MIN_DISTINCT_SOURCES",
                5,
                minimum=1,
            ),
            computational_min_aggregate_confidence=_read_float_env(
                "MED13_RELATION_AUTOPROMOTE_COMPUTATIONAL_MIN_AGGREGATE_CONFIDENCE",
                0.99,
            ),
            conflicting_confidence_threshold=_read_float_env(
                "MED13_RELATION_AUTOPROMOTE_CONFLICTING_CONFIDENCE_THRESHOLD",
                0.5,
            ),
        )


@dataclass(frozen=True)
class AutoPromotionDecision:
    """Outcome details for one relation auto-promotion evaluation."""

    outcome: Literal["promoted", "kept"]
    reason: str
    previous_status: str
    current_status: str
    all_computational: bool
    required_sources: int
    required_confidence: float
    distinct_source_count: int
    distinct_document_count: int
    distinct_run_count: int
    aggregate_confidence: float
    highest_evidence_tier: str | None


def _as_uuid(value: str | UUID) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))


def _try_as_uuid(value: str | UUID | None) -> UUID | None:
    if value is None:
        return None
    if isinstance(value, UUID):
        return value
    normalized = value.strip()
    if not normalized:
        return None
    try:
        return UUID(normalized)
    except ValueError:
        return None


def _clamp_confidence(value: float) -> float:
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return value


def _normalize_evidence_tier(value: str | None) -> str:
    if value is None:
        return _DEFAULT_EVIDENCE_TIER
    normalized = value.strip().upper()
    if not normalized:
        return _DEFAULT_EVIDENCE_TIER
    return normalized


def _tier_rank(value: str | None) -> int:
    if value is None:
        return 0
    return _EVIDENCE_TIER_RANK.get(value.strip().upper(), 0)


__all__ = [
    "AutoPromotionDecision",
    "AutoPromotionPolicy",
    "_DEFAULT_EVIDENCE_TIER",
    "_PROMOTABLE_CURATION_STATUSES",
    "_SPACE_POLICY_CUSTOM_PREFIX",
    "_SPACE_POLICY_SETTINGS_KEY",
    "_as_uuid",
    "_clamp_confidence",
    "_normalize_evidence_tier",
    "_normalize_tier_setting",
    "_parse_bool_setting",
    "_parse_float_setting",
    "_parse_int_setting",
    "_tier_rank",
    "_try_as_uuid",
]
