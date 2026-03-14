"""Graph-core contracts for heuristic extraction fallback behavior."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class ExtractionHeuristicRelation:
    """Pack-owned heuristic relation emitted by deterministic extraction fallback."""

    source_type: str
    relation_type: str
    target_type: str
    polarity: Literal["SUPPORT", "REFUTE", "UNCERTAIN", "HYPOTHESIS"] = "UNCERTAIN"


@dataclass(frozen=True)
class ExtractionHeuristicConfig:
    """Pack-owned extraction fallback defaults."""

    relation_when_variant_and_phenotype_present: ExtractionHeuristicRelation
    claim_text_fields: tuple[str, ...]
