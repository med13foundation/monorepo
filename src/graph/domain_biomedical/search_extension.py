"""Biomedical graph search extension wiring."""

from __future__ import annotations

from src.graph.core.search_extension import GraphSearchConfig, GraphSearchExtension
from src.infrastructure.llm.prompts.graph_search import GRAPH_SEARCH_SYSTEM_PROMPT

BIOMEDICAL_GRAPH_SEARCH_EXTENSION = GraphSearchConfig(
    system_prompt=GRAPH_SEARCH_SYSTEM_PROMPT,
)


def get_biomedical_graph_search_extension() -> GraphSearchExtension:
    """Return the biomedical-pack graph search extension."""
    return BIOMEDICAL_GRAPH_SEARCH_EXTENSION
