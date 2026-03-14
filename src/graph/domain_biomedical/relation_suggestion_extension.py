"""Biomedical relation-suggestion extension wiring."""

from __future__ import annotations

from src.graph.core.relation_suggestion_extension import (
    GraphRelationSuggestionConfig,
    GraphRelationSuggestionExtension,
)

BIOMEDICAL_RELATION_SUGGESTION_EXTENSION = GraphRelationSuggestionConfig()


def get_biomedical_relation_suggestion_extension() -> GraphRelationSuggestionExtension:
    """Return the biomedical-pack relation suggestion extension."""
    return BIOMEDICAL_RELATION_SUGGESTION_EXTENSION
