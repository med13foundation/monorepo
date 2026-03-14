"""Biomedical graph view configuration."""

from __future__ import annotations

from src.graph.core.view_config import GraphViewConfig, GraphViewExtension

_BIOMEDICAL_GRAPH_VIEW_CONFIG = GraphViewConfig(
    entity_view_types={
        "gene": "GENE",
        "variant": "VARIANT",
        "phenotype": "PHENOTYPE",
    },
    document_view_types=frozenset({"paper"}),
    claim_view_types=frozenset({"claim"}),
    mechanism_relation_types=frozenset(
        {
            "CAUSES",
            "UPSTREAM_OF",
            "DOWNSTREAM_OF",
            "REFINES",
            "SUPPORTS",
            "GENERALIZES",
            "INSTANCE_OF",
        },
    ),
)


def get_biomedical_graph_view_extension() -> GraphViewExtension:
    """Return the biomedical-pack graph view extension."""
    return _BIOMEDICAL_GRAPH_VIEW_CONFIG


def normalize_biomedical_graph_view_type(value: str) -> str:
    """Normalize one biomedical graph view type."""
    return _BIOMEDICAL_GRAPH_VIEW_CONFIG.normalize_view_type(value)
