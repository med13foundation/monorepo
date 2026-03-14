"""Biomedical-pack graph-connection prompt dispatch."""

from __future__ import annotations

from src.graph.core.graph_connection_prompt import GraphConnectionPromptConfig
from src.infrastructure.llm.prompts.graph_connection import (
    CLINVAR_GRAPH_CONNECTION_DISCOVERY_SYSTEM_PROMPT,
    CLINVAR_GRAPH_CONNECTION_SYNTHESIS_SYSTEM_PROMPT,
    PUBMED_GRAPH_CONNECTION_DISCOVERY_SYSTEM_PROMPT,
    PUBMED_GRAPH_CONNECTION_SYNTHESIS_SYSTEM_PROMPT,
)

BIOMEDICAL_GRAPH_CONNECTION_PROMPT_CONFIG = GraphConnectionPromptConfig(
    default_source_type="clinvar",
    system_prompts_by_source_type={
        "clinvar": (
            f"{CLINVAR_GRAPH_CONNECTION_DISCOVERY_SYSTEM_PROMPT}\n\n"
            f"{CLINVAR_GRAPH_CONNECTION_SYNTHESIS_SYSTEM_PROMPT}"
        ),
        "pubmed": (
            f"{PUBMED_GRAPH_CONNECTION_DISCOVERY_SYSTEM_PROMPT}\n\n"
            f"{PUBMED_GRAPH_CONNECTION_SYNTHESIS_SYSTEM_PROMPT}"
        ),
    },
)
