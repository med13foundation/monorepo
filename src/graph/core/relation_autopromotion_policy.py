"""Graph-core relation auto-promotion policy contracts and helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from src.graph.core.relation_autopromotion_env import (
    _ENV_BLOCK_CONFLICTING_EVIDENCE,
    _ENV_COMPUTATIONAL_MIN_AGGREGATE_CONFIDENCE,
    _ENV_COMPUTATIONAL_MIN_DISTINCT_SOURCES,
    _ENV_CONFLICTING_CONFIDENCE_THRESHOLD,
    _ENV_ENABLED,
    _ENV_MIN_AGGREGATE_CONFIDENCE,
    _ENV_MIN_DISTINCT_SOURCES,
    _ENV_REQUIRE_DISTINCT_DOCUMENTS,
    _ENV_REQUIRE_DISTINCT_RUNS,
    read_graph_relation_autopromote_bool,
    read_graph_relation_autopromote_float,
    read_graph_relation_autopromote_int,
    read_graph_relation_autopromote_tier,
)

if TYPE_CHECKING:
    from src.graph.core.relation_autopromotion_defaults import (
        RelationAutopromotionDefaults,
    )

DEFAULT_RELATION_AUTOPROMOTION_EVIDENCE_TIER = "COMPUTATIONAL"
RELATION_AUTOPROMOTION_EVIDENCE_TIER_RANK: dict[str, int] = {
    "EXPERT_CURATED": 6,
    "CLINICAL": 5,
    "EXPERIMENTAL": 4,
    "LITERATURE": 3,
    "STRUCTURED_DATA": 2,
    "COMPUTATIONAL": 1,
}
PROMOTABLE_RELATION_CURATION_STATUSES = {"DRAFT", "UNDER_REVIEW"}
DEFAULT_RELATION_AUTOPROMOTION_MIN_EVIDENCE_TIER = "LITERATURE"
RELATION_AUTOPROMOTION_SPACE_POLICY_SETTINGS_KEY = "relation_auto_promotion"
RELATION_AUTOPROMOTION_SPACE_POLICY_CUSTOM_PREFIX = "relation_autopromote_"


def parse_relation_autopromotion_bool(value: object, *, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return default


def parse_relation_autopromotion_int(
    value: object,
    *,
    default: int,
    minimum: int = 0,
) -> int:
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


def parse_relation_autopromotion_float(
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


def normalize_relation_autopromotion_tier(value: object, *, default: str) -> str:
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
    min_evidence_tier: str = DEFAULT_RELATION_AUTOPROMOTION_MIN_EVIDENCE_TIER
    computational_min_distinct_sources: int = 5
    computational_min_aggregate_confidence: float = 0.99
    conflicting_confidence_threshold: float = 0.5

    @classmethod
    def from_environment(
        cls,
        *,
        defaults: RelationAutopromotionDefaults,
    ) -> AutoPromotionPolicy:
        normalized_tier = read_graph_relation_autopromote_tier(
            defaults.min_evidence_tier,
        )
        if not normalized_tier:
            normalized_tier = defaults.min_evidence_tier
        return cls(
            enabled=read_graph_relation_autopromote_bool(
                _ENV_ENABLED,
                default=defaults.enabled,
            ),
            min_distinct_sources=read_graph_relation_autopromote_int(
                _ENV_MIN_DISTINCT_SOURCES,
                defaults.min_distinct_sources,
                minimum=1,
            ),
            min_aggregate_confidence=read_graph_relation_autopromote_float(
                _ENV_MIN_AGGREGATE_CONFIDENCE,
                defaults.min_aggregate_confidence,
            ),
            require_distinct_documents=read_graph_relation_autopromote_bool(
                _ENV_REQUIRE_DISTINCT_DOCUMENTS,
                default=defaults.require_distinct_documents,
            ),
            require_distinct_runs=read_graph_relation_autopromote_bool(
                _ENV_REQUIRE_DISTINCT_RUNS,
                default=defaults.require_distinct_runs,
            ),
            block_if_conflicting_evidence=read_graph_relation_autopromote_bool(
                _ENV_BLOCK_CONFLICTING_EVIDENCE,
                default=defaults.block_if_conflicting_evidence,
            ),
            min_evidence_tier=normalized_tier,
            computational_min_distinct_sources=read_graph_relation_autopromote_int(
                _ENV_COMPUTATIONAL_MIN_DISTINCT_SOURCES,
                defaults.computational_min_distinct_sources,
                minimum=1,
            ),
            computational_min_aggregate_confidence=read_graph_relation_autopromote_float(
                _ENV_COMPUTATIONAL_MIN_AGGREGATE_CONFIDENCE,
                defaults.computational_min_aggregate_confidence,
            ),
            conflicting_confidence_threshold=read_graph_relation_autopromote_float(
                _ENV_CONFLICTING_CONFIDENCE_THRESHOLD,
                defaults.conflicting_confidence_threshold,
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


def normalize_relation_evidence_tier(value: str | None) -> str:
    if value is None:
        return DEFAULT_RELATION_AUTOPROMOTION_EVIDENCE_TIER
    normalized = value.strip().upper()
    if not normalized:
        return DEFAULT_RELATION_AUTOPROMOTION_EVIDENCE_TIER
    return normalized


def relation_evidence_tier_rank(value: str | None) -> int:
    if value is None:
        return 0
    return RELATION_AUTOPROMOTION_EVIDENCE_TIER_RANK.get(value.strip().upper(), 0)
