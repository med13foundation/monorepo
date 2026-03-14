"""Unit tests for pack-aware graph domain-context resolution."""

from __future__ import annotations

from src.graph.core.domain_context import (
    default_graph_domain_context_for_source_type,
    resolve_graph_domain_context,
)
from src.graph.domain_biomedical.domain_context import (
    BIOMEDICAL_GRAPH_DOMAIN_CONTEXT_POLICY,
)


def test_default_graph_domain_context_for_source_type_uses_provided_policy() -> None:
    assert (
        default_graph_domain_context_for_source_type(
            "pubmed",
            domain_context_policy=BIOMEDICAL_GRAPH_DOMAIN_CONTEXT_POLICY,
        )
        == "clinical"
    )
    assert (
        default_graph_domain_context_for_source_type(
            "clinvar",
            domain_context_policy=BIOMEDICAL_GRAPH_DOMAIN_CONTEXT_POLICY,
        )
        == "genomics"
    )


def test_resolve_graph_domain_context_prefers_metadata_over_source_default() -> None:
    resolved = resolve_graph_domain_context(
        domain_context_policy=BIOMEDICAL_GRAPH_DOMAIN_CONTEXT_POLICY,
        metadata={"domain_context": "cardiology"},
        source_type="pubmed",
        fallback="general",
    )

    assert resolved == "cardiology"


def test_resolve_graph_domain_context_uses_provided_source_default() -> None:
    resolved = resolve_graph_domain_context(
        domain_context_policy=BIOMEDICAL_GRAPH_DOMAIN_CONTEXT_POLICY,
        source_type="pubmed",
        fallback=None,
    )

    assert resolved == "clinical"
