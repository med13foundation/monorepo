"""Biomedical-pack extraction fallback defaults."""

from __future__ import annotations

from src.graph.core.extraction_fallback import (
    ExtractionHeuristicConfig,
    ExtractionHeuristicRelation,
)

BIOMEDICAL_EXTRACTION_HEURISTIC_CONFIG = ExtractionHeuristicConfig(
    relation_when_variant_and_phenotype_present=ExtractionHeuristicRelation(
        source_type="VARIANT",
        relation_type="ASSOCIATED_WITH",
        target_type="PHENOTYPE",
        polarity="UNCERTAIN",
    ),
    claim_text_fields=("abstract", "text", "full_text", "title"),
)
