"""
Kernel relation repository interface.

Defines the abstract contract for graph-edge CRUD against the
``relations`` table, including curation lifecycle and neighborhood traversal.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import datetime

    from src.models.database.kernel.relations import RelationModel


class KernelRelationRepository(ABC):
    """
    Graph-edge repository with curation lifecycle.

    Relations link two entities with a typed, directed edge and
    carry evidence metadata and a curation status.
    """

    # ── Write ─────────────────────────────────────────────────────────

    @abstractmethod
    def create(  # noqa: PLR0913
        self,
        *,
        study_id: str,
        source_id: str,
        relation_type: str,
        target_id: str,
        confidence: float = 0.5,
        evidence_summary: str | None = None,
        evidence_tier: str | None = None,
        curation_status: str = "DRAFT",
        provenance_id: str | None = None,
    ) -> RelationModel:
        """Create a new relation (graph edge) between two entities."""

    # ── Read ──────────────────────────────────────────────────────────

    @abstractmethod
    def get_by_id(self, relation_id: str) -> RelationModel | None:
        """Retrieve a single relation by primary key."""

    @abstractmethod
    def find_by_source(
        self,
        source_id: str,
        *,
        relation_type: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[RelationModel]:
        """All outgoing edges from a source entity."""

    @abstractmethod
    def find_by_target(
        self,
        target_id: str,
        *,
        relation_type: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[RelationModel]:
        """All incoming edges to a target entity."""

    @abstractmethod
    def find_neighborhood(
        self,
        entity_id: str,
        *,
        depth: int = 1,
        relation_types: list[str] | None = None,
    ) -> list[RelationModel]:
        """
        Multi-hop graph traversal around an entity.

        Returns all relations within ``depth`` hops, optionally
        filtered by relation type.
        """

    @abstractmethod
    def find_by_study(
        self,
        study_id: str,
        *,
        relation_type: str | None = None,
        curation_status: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[RelationModel]:
        """Paginated listing of relations in a study with optional filters."""

    # ── Curation lifecycle ────────────────────────────────────────────

    @abstractmethod
    def update_curation(
        self,
        relation_id: str,
        *,
        curation_status: str,
        reviewed_by: str,
        reviewed_at: datetime | None = None,
    ) -> RelationModel:
        """Update the curation status of a relation (DRAFT → APPROVED etc.)."""

    # ── Delete ────────────────────────────────────────────────────────

    @abstractmethod
    def delete(self, relation_id: str) -> bool:
        """Delete a relation."""

    @abstractmethod
    def delete_by_provenance(self, provenance_id: str) -> int:
        """Delete all relations linked to a provenance record. Returns count."""


__all__ = ["KernelRelationRepository"]
