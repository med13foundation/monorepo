"""Pack-owned defaults for relation auto-promotion policy."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RelationAutopromotionDefaults:
    enabled: bool = True
    min_distinct_sources: int = 3
    min_aggregate_confidence: float = 0.95
    require_distinct_documents: bool = True
    require_distinct_runs: bool = True
    block_if_conflicting_evidence: bool = True
    min_evidence_tier: str = "LITERATURE"
    computational_min_distinct_sources: int = 5
    computational_min_aggregate_confidence: float = 0.99
    conflicting_confidence_threshold: float = 0.5
