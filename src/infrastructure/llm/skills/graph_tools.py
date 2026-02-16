"""Skill builders for graph query and graph-relation upsert operations."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from src.type_definitions.json_utils import to_json_value

if TYPE_CHECKING:
    from collections.abc import Callable

    from src.domain.ports.graph_query_port import GraphQueryPort
    from src.domain.repositories.kernel.relation_repository import (
        KernelRelationRepository,
    )
    from src.type_definitions.common import JSONObject, JSONValue
else:
    type JSONObject = dict[str, object]
    type JSONValue = object


def _model_to_json(model: object) -> JSONObject:
    dump_method = getattr(model, "model_dump", None)
    if not callable(dump_method):
        msg = "Expected a Pydantic model with model_dump()"
        raise TypeError(msg)
    payload = dump_method(mode="json")
    if not isinstance(payload, dict):
        msg = "Expected model_dump(mode='json') to return a dictionary"
        raise TypeError(msg)
    return {str(key): to_json_value(value) for key, value in payload.items()}


def _normalize_space_id(research_space_id: str | None) -> str:
    if research_space_id is None:
        msg = "research_space_id is required for graph tools"
        raise ValueError(msg)
    normalized = research_space_id.strip()
    if not normalized:
        msg = "research_space_id is required for graph tools"
        raise ValueError(msg)
    return normalized


def make_graph_query_neighbourhood_tool(
    *,
    graph_query_service: GraphQueryPort,
    research_space_id: str | None = None,
    **_: object,
) -> Callable[[str, int, list[str] | None, int], list[JSONObject]]:
    """Build a graph_query_neighbourhood tool callable."""
    space_id = _normalize_space_id(research_space_id)

    def graph_query_neighbourhood(
        entity_id: str,
        depth: int = 1,
        relation_types: list[str] | None = None,
        limit: int = 200,
    ) -> list[JSONObject]:
        relations = graph_query_service.graph_query_neighbourhood(
            research_space_id=space_id,
            entity_id=entity_id,
            depth=depth,
            relation_types=relation_types,
            limit=limit,
        )
        return [_model_to_json(relation) for relation in relations]

    return graph_query_neighbourhood


def make_graph_query_entities_tool(
    *,
    graph_query_service: GraphQueryPort,
    research_space_id: str | None = None,
    **_: object,
) -> Callable[[str | None, str | None, int], list[JSONObject]]:
    """Build a graph_query_entities tool callable."""
    space_id = _normalize_space_id(research_space_id)

    def graph_query_entities(
        entity_type: str | None = None,
        query_text: str | None = None,
        limit: int = 200,
    ) -> list[JSONObject]:
        entities = graph_query_service.graph_query_entities(
            research_space_id=space_id,
            entity_type=entity_type,
            query_text=query_text,
            limit=limit,
        )
        return [_model_to_json(entity) for entity in entities]

    return graph_query_entities


def make_graph_query_shared_subjects_tool(
    *,
    graph_query_service: GraphQueryPort,
    research_space_id: str | None = None,
    **_: object,
) -> Callable[[str, str, int], list[JSONObject]]:
    """Build a graph_query_shared_subjects tool callable."""
    space_id = _normalize_space_id(research_space_id)

    def graph_query_shared_subjects(
        entity_id_a: str,
        entity_id_b: str,
        limit: int = 100,
    ) -> list[JSONObject]:
        entities = graph_query_service.graph_query_shared_subjects(
            research_space_id=space_id,
            entity_id_a=entity_id_a,
            entity_id_b=entity_id_b,
            limit=limit,
        )
        return [_model_to_json(entity) for entity in entities]

    return graph_query_shared_subjects


def make_graph_query_relations_tool(
    *,
    graph_query_service: GraphQueryPort,
    research_space_id: str | None = None,
    **_: object,
) -> Callable[
    [str, list[str] | None, Literal["outgoing", "incoming", "both"], int, int],
    list[JSONObject],
]:
    """Build a graph_query_relations tool callable."""
    space_id = _normalize_space_id(research_space_id)

    def graph_query_relations(
        entity_id: str,
        relation_types: list[str] | None = None,
        direction: Literal["outgoing", "incoming", "both"] = "both",
        depth: int = 1,
        limit: int = 200,
    ) -> list[JSONObject]:
        relations = graph_query_service.graph_query_relations(
            research_space_id=space_id,
            entity_id=entity_id,
            relation_types=relation_types,
            direction=direction,
            depth=depth,
            limit=limit,
        )
        return [_model_to_json(relation) for relation in relations]

    return graph_query_relations


def make_graph_query_observations_tool(
    *,
    graph_query_service: GraphQueryPort,
    research_space_id: str | None = None,
    **_: object,
) -> Callable[[str, list[str] | None, int], list[JSONObject]]:
    """Build a graph_query_observations tool callable."""
    space_id = _normalize_space_id(research_space_id)

    def graph_query_observations(
        entity_id: str,
        variable_ids: list[str] | None = None,
        limit: int = 200,
    ) -> list[JSONObject]:
        observations = graph_query_service.graph_query_observations(
            research_space_id=space_id,
            entity_id=entity_id,
            variable_ids=variable_ids,
            limit=limit,
        )
        return [_model_to_json(observation) for observation in observations]

    return graph_query_observations


def make_graph_query_by_observation_tool(
    *,
    graph_query_service: GraphQueryPort,
    research_space_id: str | None = None,
    **_: object,
) -> Callable[
    [str, Literal["eq", "lt", "lte", "gt", "gte", "contains"], JSONValue | None, int],
    list[JSONObject],
]:
    """Build a graph_query_by_observation tool callable."""
    space_id = _normalize_space_id(research_space_id)

    def graph_query_by_observation(
        variable_id: str,
        operator: Literal["eq", "lt", "lte", "gt", "gte", "contains"] = "eq",
        value: JSONValue | None = None,
        limit: int = 200,
    ) -> list[JSONObject]:
        entities = graph_query_service.graph_query_by_observation(
            research_space_id=space_id,
            variable_id=variable_id,
            operator=operator,
            value=value,
            limit=limit,
        )
        return [_model_to_json(entity) for entity in entities]

    return graph_query_by_observation


def make_graph_query_relation_evidence_tool(
    *,
    graph_query_service: GraphQueryPort,
    research_space_id: str | None = None,
    **_: object,
) -> Callable[[str, int], list[JSONObject]]:
    """Build a graph_query_relation_evidence tool callable."""
    space_id = _normalize_space_id(research_space_id)

    def graph_query_relation_evidence(
        relation_id: str,
        limit: int = 200,
    ) -> list[JSONObject]:
        evidences = graph_query_service.graph_query_relation_evidence(
            research_space_id=space_id,
            relation_id=relation_id,
            limit=limit,
        )
        return [_model_to_json(evidence) for evidence in evidences]

    return graph_query_relation_evidence


def make_graph_aggregate_tool(
    *,
    graph_query_service: GraphQueryPort,
    research_space_id: str | None = None,
    **_: object,
) -> Callable[[str, str | None, Literal["count", "mean", "min", "max"]], JSONObject]:
    """Build a graph_aggregate tool callable."""
    space_id = _normalize_space_id(research_space_id)

    def graph_aggregate(
        variable_id: str,
        entity_type: str | None = None,
        aggregation: Literal["count", "mean", "min", "max"] = "count",
    ) -> JSONObject:
        return graph_query_service.graph_aggregate(
            research_space_id=space_id,
            variable_id=variable_id,
            entity_type=entity_type,
            aggregation=aggregation,
        )

    return graph_aggregate


def make_upsert_relation_tool(
    *,
    relation_repository: KernelRelationRepository,
    research_space_id: str | None = None,
    **_: object,
) -> Callable[[str, str, str, float, str | None, str | None, str | None], JSONObject]:
    """Build an upsert_relation tool callable backed by canonical relation upsert."""
    space_id = _normalize_space_id(research_space_id)

    def upsert_relation(  # noqa: PLR0913
        source_id: str,
        relation_type: str,
        target_id: str,
        confidence: float = 0.5,
        evidence_summary: str | None = None,
        evidence_tier: str | None = "COMPUTATIONAL",
        provenance_id: str | None = None,
    ) -> JSONObject:
        relation = relation_repository.create(
            research_space_id=space_id,
            source_id=source_id,
            relation_type=relation_type,
            target_id=target_id,
            confidence=confidence,
            evidence_summary=evidence_summary,
            evidence_tier=evidence_tier,
            provenance_id=provenance_id,
        )
        return _model_to_json(relation)

    return upsert_relation


__all__ = [
    "make_graph_aggregate_tool",
    "make_graph_query_by_observation_tool",
    "make_graph_query_entities_tool",
    "make_graph_query_neighbourhood_tool",
    "make_graph_query_observations_tool",
    "make_graph_query_relations_tool",
    "make_graph_query_relation_evidence_tool",
    "make_graph_query_shared_subjects_tool",
    "make_upsert_relation_tool",
]
