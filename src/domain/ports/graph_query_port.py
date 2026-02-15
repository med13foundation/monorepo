"""Domain port for graph-layer read operations used by graph agents."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.domain.entities.kernel.entities import KernelEntity
    from src.domain.entities.kernel.observations import KernelObservation
    from src.domain.entities.kernel.relations import (
        KernelRelation,
        KernelRelationEvidence,
    )


class GraphQueryPort(ABC):
    """Read-oriented graph query interface for graph-layer agents."""

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


__all__ = ["GraphQueryPort"]
