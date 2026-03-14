"""Unit tests for biomedical graph view configuration."""

from __future__ import annotations

import pytest

from src.graph.domain_biomedical.view_config import (
    get_biomedical_graph_view_extension,
    normalize_biomedical_graph_view_type,
)


def test_normalize_biomedical_graph_view_type_supports_known_views() -> None:
    assert normalize_biomedical_graph_view_type("Gene") == "gene"
    assert normalize_biomedical_graph_view_type("variant") == "variant"
    assert normalize_biomedical_graph_view_type("PHENOTYPE") == "phenotype"
    assert normalize_biomedical_graph_view_type("paper") == "paper"
    assert normalize_biomedical_graph_view_type("claim") == "claim"


def test_normalize_biomedical_graph_view_type_rejects_unknown_views() -> None:
    with pytest.raises(ValueError, match="Unsupported graph view type"):
        normalize_biomedical_graph_view_type("pathway")


def test_biomedical_graph_view_extension_exposes_entity_mapping() -> None:
    config = get_biomedical_graph_view_extension()

    assert config.entity_view_types["gene"] == "GENE"
    assert "paper" in config.document_view_types
    assert "claim" in config.claim_view_types
    assert "CAUSES" in config.mechanism_relation_types
