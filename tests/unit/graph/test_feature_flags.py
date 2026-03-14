"""Unit tests for graph feature-flag resolution."""

from __future__ import annotations

import pytest

from src.graph.core.feature_flags import is_flag_enabled
from src.graph.domain_biomedical.feature_flags import BIOMEDICAL_GRAPH_FEATURE_FLAGS


def test_primary_graph_flag_is_used(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        BIOMEDICAL_GRAPH_FEATURE_FLAGS.entity_embeddings.primary_env_name,
        "1",
    )

    assert is_flag_enabled(BIOMEDICAL_GRAPH_FEATURE_FLAGS.entity_embeddings) is True


def test_biomedical_graph_flags_have_no_legacy_aliases() -> None:
    assert BIOMEDICAL_GRAPH_FEATURE_FLAGS.entity_embeddings.legacy_env_name is None
    assert BIOMEDICAL_GRAPH_FEATURE_FLAGS.relation_suggestions.legacy_env_name is None
    assert BIOMEDICAL_GRAPH_FEATURE_FLAGS.hypothesis_generation.legacy_env_name is None
    assert BIOMEDICAL_GRAPH_FEATURE_FLAGS.search_agent.legacy_env_name is None


def test_feature_flag_display_name_uses_primary_env_only() -> None:
    assert (
        BIOMEDICAL_GRAPH_FEATURE_FLAGS.entity_embeddings.env_display_name
        == "GRAPH_ENABLE_ENTITY_EMBEDDINGS=1"
    )


def test_graph_search_agent_defaults_to_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(
        BIOMEDICAL_GRAPH_FEATURE_FLAGS.search_agent.primary_env_name,
        raising=False,
    )

    assert is_flag_enabled(BIOMEDICAL_GRAPH_FEATURE_FLAGS.search_agent) is True
