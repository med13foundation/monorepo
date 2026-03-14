"""Biomedical source-type domain-context defaults."""

from __future__ import annotations

from src.graph.core.domain_context_policy import (
    GraphDomainContextPolicy,
    SourceTypeDomainContextDefault,
)

BIOMEDICAL_GRAPH_DOMAIN_CONTEXT_POLICY = GraphDomainContextPolicy(
    source_type_defaults=(
        SourceTypeDomainContextDefault(
            source_type="pubmed",
            domain_context="clinical",
        ),
        SourceTypeDomainContextDefault(
            source_type="clinvar",
            domain_context="genomics",
        ),
    ),
)
