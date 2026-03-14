"""Tests for graph-core read-model contracts."""

from __future__ import annotations

import pytest

from src.graph.core.read_model import (
    CORE_GRAPH_READ_MODELS,
    GraphReadModelAuthoritativeSource,
    GraphReadModelDefinition,
    GraphReadModelOwner,
    GraphReadModelRegistry,
    GraphReadModelTrigger,
    build_core_graph_read_model_registry,
)


def test_graph_read_model_definition_requires_authoritative_source() -> None:
    with pytest.raises(
        ValueError,
        match="must declare authoritative sources",
    ):
        GraphReadModelDefinition(
            name="invalid_model",
            description="invalid",
            owner=GraphReadModelOwner.GRAPH_CORE,
            authoritative_sources=(),
            triggers=(GraphReadModelTrigger.FULL_REBUILD,),
        )


def test_graph_read_model_definition_requires_full_rebuild() -> None:
    with pytest.raises(ValueError, match="must support full rebuild"):
        GraphReadModelDefinition(
            name="invalid_model",
            description="invalid",
            owner=GraphReadModelOwner.GRAPH_CORE,
            authoritative_sources=(GraphReadModelAuthoritativeSource.CANONICAL_GRAPH,),
            triggers=(GraphReadModelTrigger.PROJECTION_CHANGE,),
        )


def test_graph_read_model_registry_rejects_duplicate_names() -> None:
    registry = GraphReadModelRegistry()
    definition = GraphReadModelDefinition(
        name="entity_neighbors",
        description="duplicate",
        owner=GraphReadModelOwner.GRAPH_CORE,
        authoritative_sources=(GraphReadModelAuthoritativeSource.CANONICAL_GRAPH,),
        triggers=(GraphReadModelTrigger.FULL_REBUILD,),
    )

    registry.register(definition)

    with pytest.raises(ValueError, match="already registered"):
        registry.register(definition)


def test_core_graph_read_model_registry_contains_phase4_catalog() -> None:
    registry = build_core_graph_read_model_registry()

    assert tuple(definition.name for definition in CORE_GRAPH_READ_MODELS) == (
        "entity_neighbors",
        "entity_relation_summary",
        "entity_claim_summary",
        "entity_mechanism_paths",
    )
    assert tuple(definition.name for definition in registry.list()) == (
        "entity_neighbors",
        "entity_relation_summary",
        "entity_claim_summary",
        "entity_mechanism_paths",
    )
    assert all(
        definition.owner == GraphReadModelOwner.GRAPH_CORE
        for definition in registry.list()
    )
    assert all(not definition.is_truth_source for definition in registry.list())
    assert all(
        GraphReadModelTrigger.FULL_REBUILD in definition.triggers
        for definition in registry.list()
    )
    assert registry.get("entity_claim_summary") is not None
    assert registry.get("entity_mechanism_paths") is not None
    assert registry.get("missing_model") is None
