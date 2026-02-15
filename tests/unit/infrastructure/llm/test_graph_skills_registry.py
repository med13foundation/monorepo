"""Tests for graph skill registration and graph tool building."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from unittest.mock import Mock
from uuid import uuid4

from src.domain.entities.kernel.entities import KernelEntity
from src.domain.entities.kernel.observations import KernelObservation
from src.domain.entities.kernel.relations import KernelRelation, KernelRelationEvidence
from src.infrastructure.llm.skills.registry import (
    build_graph_connection_tools,
    build_graph_search_tools,
    get_skill_registry,
    register_all_skills,
)

if TYPE_CHECKING:
    from collections.abc import Callable


def _tool_by_name(tools: list[object], name: str) -> Callable[..., object]:
    for tool in tools:
        tool_name = getattr(tool, "__name__", "")
        if tool_name == name and callable(tool):
            return tool
    msg = f"Tool '{name}' not found"
    raise AssertionError(msg)


def _build_relation() -> KernelRelation:
    now = datetime.now(UTC)
    return KernelRelation(
        id=uuid4(),
        research_space_id=uuid4(),
        source_id=uuid4(),
        relation_type="ASSOCIATED_WITH",
        target_id=uuid4(),
        aggregate_confidence=0.8,
        source_count=2,
        highest_evidence_tier="LITERATURE",
        curation_status="DRAFT",
        provenance_id=None,
        reviewed_by=None,
        reviewed_at=None,
        created_at=now,
        updated_at=now,
    )


def _build_entity() -> KernelEntity:
    now = datetime.now(UTC)
    return KernelEntity(
        id=uuid4(),
        research_space_id=uuid4(),
        entity_type="GENE",
        display_label="MED13",
        metadata_payload={},
        created_at=now,
        updated_at=now,
    )


def _build_observation() -> KernelObservation:
    now = datetime.now(UTC)
    return KernelObservation(
        id=uuid4(),
        research_space_id=uuid4(),
        subject_id=uuid4(),
        variable_id="VAR_TEST",
        value_numeric=None,
        value_text="pathogenic",
        value_date=None,
        value_coded=None,
        value_boolean=None,
        value_json=None,
        unit=None,
        observed_at=None,
        provenance_id=None,
        confidence=0.9,
        created_at=now,
        updated_at=now,
    )


def _build_evidence() -> KernelRelationEvidence:
    now = datetime.now(UTC)
    return KernelRelationEvidence(
        id=uuid4(),
        relation_id=uuid4(),
        confidence=0.7,
        evidence_summary="shared profile evidence",
        evidence_tier="COMPUTATIONAL",
        provenance_id=None,
        source_document_id=None,
        agent_run_id=None,
        created_at=now,
    )


def test_register_all_skills_includes_graph_skills() -> None:
    register_all_skills()
    registry = get_skill_registry()
    available = set(registry.list_skills())
    assert "graph_query_neighbourhood" in available
    assert "graph_query_entities" in available
    assert "graph_query_relations" in available
    assert "graph_query_shared_subjects" in available
    assert "graph_query_observations" in available
    assert "graph_query_by_observation" in available
    assert "graph_aggregate" in available
    assert "graph_query_relation_evidence" in available
    assert "upsert_relation" in available


def test_build_graph_connection_tools_calls_dependencies() -> None:
    dictionary_service = Mock()
    dictionary_service.is_relation_allowed.return_value = True
    dictionary_service.requires_evidence.return_value = True
    graph_query_service = Mock()
    graph_query_service.graph_query_neighbourhood.return_value = [_build_relation()]
    graph_query_service.graph_query_shared_subjects.return_value = [_build_entity()]
    graph_query_service.graph_query_observations.return_value = [_build_observation()]
    graph_query_service.graph_query_relation_evidence.return_value = [_build_evidence()]
    relation_repository = Mock()
    relation_repository.create.return_value = _build_relation()

    tools = build_graph_connection_tools(
        dictionary_service=dictionary_service,
        graph_query_service=graph_query_service,
        relation_repository=relation_repository,
        research_space_id=str(uuid4()),
    )

    neighbourhood_tool = _tool_by_name(tools, "graph_query_neighbourhood")
    shared_subjects_tool = _tool_by_name(tools, "graph_query_shared_subjects")
    observations_tool = _tool_by_name(tools, "graph_query_observations")
    evidence_tool = _tool_by_name(tools, "graph_query_relation_evidence")
    upsert_tool = _tool_by_name(tools, "upsert_relation")
    validate_triple = _tool_by_name(tools, "validate_triple")

    neighbourhood = neighbourhood_tool("entity-1")
    assert neighbourhood[0]["relation_type"] == "ASSOCIATED_WITH"

    shared_subjects = shared_subjects_tool("entity-1", "entity-2")
    assert shared_subjects[0]["entity_type"] == "GENE"

    observations = observations_tool("entity-1")
    assert observations[0]["variable_id"] == "VAR_TEST"

    evidence = evidence_tool("relation-1")
    assert evidence[0]["evidence_tier"] == "COMPUTATIONAL"

    relation = upsert_tool(
        "source-1",
        "ASSOCIATED_WITH",
        "target-1",
        0.9,
        "Computed support",
        "COMPUTATIONAL",
        None,
    )
    assert relation["relation_type"] == "ASSOCIATED_WITH"
    relation_repository.create.assert_called_once()

    triple_validation = validate_triple("GENE", "ASSOCIATED_WITH", "PHENOTYPE")
    assert triple_validation["allowed"] is True
    assert triple_validation["requires_evidence"] is True


def test_build_graph_search_tools_calls_dependencies() -> None:
    graph_query_service = Mock()
    graph_query_service.graph_query_entities.return_value = [_build_entity()]
    graph_query_service.graph_query_relations.return_value = [_build_relation()]
    graph_query_service.graph_query_observations.return_value = [_build_observation()]
    graph_query_service.graph_query_by_observation.return_value = [_build_entity()]
    graph_query_service.graph_aggregate.return_value = {
        "aggregation": "count",
        "value": 1,
    }
    graph_query_service.graph_query_relation_evidence.return_value = [_build_evidence()]

    tools = build_graph_search_tools(
        graph_query_service=graph_query_service,
        research_space_id=str(uuid4()),
    )

    entities_tool = _tool_by_name(tools, "graph_query_entities")
    relations_tool = _tool_by_name(tools, "graph_query_relations")
    observations_tool = _tool_by_name(tools, "graph_query_observations")
    by_observation_tool = _tool_by_name(tools, "graph_query_by_observation")
    aggregate_tool = _tool_by_name(tools, "graph_aggregate")
    evidence_tool = _tool_by_name(tools, "graph_query_relation_evidence")

    entities = entities_tool(entity_type="GENE")
    assert entities[0]["entity_type"] == "GENE"

    relations = relations_tool("entity-1")
    assert relations[0]["relation_type"] == "ASSOCIATED_WITH"

    observations = observations_tool("entity-1")
    assert observations[0]["variable_id"] == "VAR_TEST"

    by_observation = by_observation_tool("VAR_TEST", operator="contains", value="med13")
    assert by_observation[0]["entity_type"] == "GENE"

    aggregate = aggregate_tool("VAR_TEST", aggregation="count")
    assert aggregate["value"] == 1

    evidence = evidence_tool("relation-1")
    assert evidence[0]["evidence_tier"] == "COMPUTATIONAL"
