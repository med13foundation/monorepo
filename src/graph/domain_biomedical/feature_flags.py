"""Biomedical-pack feature flags for graph runtime behavior."""

from __future__ import annotations

from src.graph.core.feature_flags import FeatureFlagDefinition, GraphFeatureFlags

ENTITY_EMBEDDINGS_FLAG = FeatureFlagDefinition(
    primary_env_name="GRAPH_ENABLE_ENTITY_EMBEDDINGS",
)
RELATION_SUGGESTIONS_FLAG = FeatureFlagDefinition(
    primary_env_name="GRAPH_ENABLE_RELATION_SUGGESTIONS",
)
HYPOTHESIS_GENERATION_FLAG = FeatureFlagDefinition(
    primary_env_name="GRAPH_ENABLE_HYPOTHESIS_GENERATION",
)
GRAPH_SEARCH_AGENT_FLAG = FeatureFlagDefinition(
    primary_env_name="GRAPH_ENABLE_SEARCH_AGENT",
    default_enabled=True,
)
BIOMEDICAL_GRAPH_FEATURE_FLAGS = GraphFeatureFlags(
    entity_embeddings=ENTITY_EMBEDDINGS_FLAG,
    relation_suggestions=RELATION_SUGGESTIONS_FLAG,
    hypothesis_generation=HYPOTHESIS_GENERATION_FLAG,
    search_agent=GRAPH_SEARCH_AGENT_FLAG,
)
