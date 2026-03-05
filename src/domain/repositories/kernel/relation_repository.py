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

    from src.domain.entities.kernel.relations import KernelRelation


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
        research_space_id: str,
        source_id: str,
        relation_type: str,
        target_id: str,
        confidence: float = 0.5,
        evidence_summary: str | None = None,
        evidence_sentence: str | None = None,
        evidence_sentence_source: str | None = None,
        evidence_sentence_confidence: str | None = None,
        evidence_sentence_rationale: str | None = None,
        evidence_tier: str | None = None,
        curation_status: str = "DRAFT",
        provenance_id: str | None = None,
        source_document_id: str | None = None,
        agent_run_id: str | None = None,
    ) -> KernelRelation:
        """Create a new relation (graph edge) between two entities."""

    # ── Read ──────────────────────────────────────────────────────────

    @abstractmethod
    def get_by_id(self, relation_id: str) -> KernelRelation | None:
        """Retrieve a single relation by primary key."""

    @abstractmethod
    def find_by_source(
        self,
        source_id: str,
        *,
        relation_type: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[KernelRelation]:
        """All outgoing edges from a source entity."""

    @abstractmethod
    def find_by_target(
        self,
        target_id: str,
        *,
        relation_type: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[KernelRelation]:
        """All incoming edges to a target entity."""

    @abstractmethod
    def find_neighborhood(
        self,
        entity_id: str,
        *,
        depth: int = 1,
        relation_types: list[str] | None = None,
        limit: int | None = None,
    ) -> list[KernelRelation]:
        """
        Multi-hop graph traversal around an entity.

        Returns all relations within ``depth`` hops, optionally
        filtered by relation type. When ``limit`` is provided, results
        are deterministically truncated after sorting by recency.
        """

    @abstractmethod
    def find_by_research_space(  # noqa: PLR0913 - query surface needs independent filters
        self,
        research_space_id: str,
        *,
        relation_type: str | None = None,
        curation_status: str | None = None,
        validation_state: str | None = None,
        source_document_id: str | None = None,
        certainty_band: str | None = None,
        node_query: str | None = None,
        node_ids: list[str] | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[KernelRelation]:
        """Paginated listing of relations in a research space with optional filters."""

    @abstractmethod
    def search_by_text(
        self,
        research_space_id: str,
        query: str,
        *,
        limit: int = 20,
    ) -> list[KernelRelation]:
        """Search relations in a research space by type, status, and evidence text."""

    # ── Curation lifecycle ────────────────────────────────────────────

    @abstractmethod
    def update_curation(
        self,
        relation_id: str,
        *,
        curation_status: str,
        reviewed_by: str,
        reviewed_at: datetime | None = None,
    ) -> KernelRelation:
        """Update the curation status of a relation (DRAFT → APPROVED etc.)."""

    # ── Delete ────────────────────────────────────────────────────────

    @abstractmethod
    def delete(self, relation_id: str) -> bool:
        """Delete a relation."""

    @abstractmethod
    def delete_by_provenance(self, provenance_id: str) -> int:
        """Delete all relations linked to a provenance record. Returns count."""

    @abstractmethod
    def count_by_research_space(  # noqa: PLR0913
        self,
        research_space_id: str,
        *,
        relation_type: str | None = None,
        curation_status: str | None = None,
        validation_state: str | None = None,
        source_document_id: str | None = None,
        certainty_band: str | None = None,
        node_query: str | None = None,
        node_ids: list[str] | None = None,
    ) -> int:
        """Count relations in a research space with optional filters."""


__all__ = ["KernelRelationRepository"]
