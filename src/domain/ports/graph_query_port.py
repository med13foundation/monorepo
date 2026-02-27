"""Domain port for graph-layer read operations used by graph agents."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from src.domain.entities.kernel.entities import KernelEntity
    from src.domain.entities.kernel.observations import KernelObservation
    from src.domain.entities.kernel.relations import (
        KernelRelation,
        KernelRelationEvidence,
    )
    from src.type_definitions.common import JSONObject, JSONValue


class GraphQueryPort(ABC):
    """Read-oriented graph query interface for graph-layer agents."""

    @abstractmethod
    def graph_query_entities(
        self,
        *,
        research_space_id: str,
        entity_type: str | None = None,
        query_text: str | None = None,
        limit: int = 200,
    ) -> list[KernelEntity]:
        """Query entities in one research space with optional filters."""

    @abstractmethod
    def graph_query_neighbourhood(
        self,
        *,
        research_space_id: str,
        entity_id: str,
        depth: int = 1,
        relation_types: list[str] | None = None,
        limit: int = 200,
    ) -> list[KernelRelation]:
        """Return relation edges around an entity within a research space."""

    @abstractmethod
    def graph_query_shared_subjects(
        self,
        *,
        research_space_id: str,
        entity_id_a: str,
        entity_id_b: str,
        limit: int = 100,
    ) -> list[KernelEntity]:
        """Return entities that co-occur with observation profiles of both seeds."""

    @abstractmethod
    def graph_query_observations(
        self,
        *,
        research_space_id: str,
        entity_id: str,
        variable_ids: list[str] | None = None,
        limit: int = 200,
    ) -> list[KernelObservation]:
        """Return observations for one entity, optionally filtered by variables."""

    @abstractmethod
    def graph_query_relation_evidence(
        self,
        *,
        research_space_id: str,
        relation_id: str,
        limit: int = 200,
    ) -> list[KernelRelationEvidence]:
        """Return evidence rows for one canonical relation."""

    @abstractmethod
    def graph_query_relations(  # noqa: PLR0913
        self,
        *,
        research_space_id: str,
        entity_id: str,
        relation_types: list[str] | None = None,
        direction: Literal["outgoing", "incoming", "both"] = "both",
        depth: int = 1,
        limit: int = 200,
    ) -> list[KernelRelation]:
        """Traverse relations from one entity with direction and depth filters."""

    @abstractmethod
    def graph_query_by_observation(  # noqa: PLR0913
        self,
        *,
        research_space_id: str,
        variable_id: str,
        operator: Literal["eq", "lt", "lte", "gt", "gte", "contains"] = "eq",
        value: JSONValue | None = None,
        limit: int = 200,
    ) -> list[KernelEntity]:
        """Find entities by observation predicate within one space."""

    @abstractmethod
    def graph_aggregate(
        self,
        *,
        research_space_id: str,
        variable_id: str,
        entity_type: str | None = None,
        aggregation: Literal["count", "mean", "min", "max"] = "count",
    ) -> JSONObject:
        """Compute aggregate statistics for one variable in one space."""


__all__ = ["GraphQueryPort"]
