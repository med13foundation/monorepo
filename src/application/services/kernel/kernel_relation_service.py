"""
Kernel relation application service.

Manages canonical relation reads, curation lifecycle,
and graph traversal for claim-backed projections.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import datetime

    from src.domain.entities.kernel.relations import KernelRelation
    from src.domain.repositories.kernel.entity_repository import (
        KernelEntityRepository,
    )
    from src.domain.repositories.kernel.relation_repository import (
        KernelRelationRepository,
    )
_ALLOWED_CURATION_STATUSES = frozenset(
    {"DRAFT", "UNDER_REVIEW", "APPROVED", "REJECTED", "RETRACTED"},
)


class KernelRelationService:
    """
    Application service for kernel relations (graph edges).

    Reads canonical claim-backed projections and manages the
    curation lifecycle for already materialized relations.
    """

    def __init__(
        self,
        relation_repo: KernelRelationRepository,
        entity_repo: KernelEntityRepository | None = None,
        *_unused_dependencies: object,
    ) -> None:
        self._relations = relation_repo
        self._entities = entity_repo

    # ── Curation lifecycle ────────────────────────────────────────────

    def update_curation_status(
        self,
        relation_id: str,
        *,
        curation_status: str,
        reviewed_by: str,
        reviewed_at: datetime | None = None,
    ) -> KernelRelation:
        """Update the curation status of a relation."""
        normalized_status = curation_status.strip().upper()
        if normalized_status not in _ALLOWED_CURATION_STATUSES:
            msg = "Invalid relation curation_status. Expected one of: " + ", ".join(
                sorted(_ALLOWED_CURATION_STATUSES),
            )
            raise ValueError(msg)
        return self._relations.update_curation(
            relation_id,
            curation_status=normalized_status,
            reviewed_by=reviewed_by,
            reviewed_at=reviewed_at,
        )

    # ── Read operations ───────────────────────────────────────────────

    def get_relation(
        self,
        relation_id: str,
        *,
        claim_backed_only: bool = True,
    ) -> KernelRelation | None:
        """Retrieve a single relation."""
        return self._relations.get_by_id(
            relation_id,
            claim_backed_only=claim_backed_only,
        )

    def get_neighborhood(
        self,
        entity_id: str,
        *,
        depth: int = 1,
        relation_types: list[str] | None = None,
        claim_backed_only: bool = True,
        limit: int | None = None,
    ) -> list[KernelRelation]:
        """Graph traversal around an entity."""
        return self._relations.find_neighborhood(
            entity_id,
            depth=depth,
            relation_types=relation_types,
            claim_backed_only=claim_backed_only,
            limit=limit,
        )

    def get_neighborhood_in_space(  # noqa: PLR0913
        self,
        research_space_id: str,
        entity_id: str,
        *,
        depth: int = 1,
        relation_types: list[str] | None = None,
        claim_backed_only: bool = True,
        limit: int | None = None,
    ) -> list[KernelRelation]:
        """
        Graph traversal around an entity, restricted to a research space.

        This protects against cross-space leakage if invalid relations exist.
        """
        if self._entities is None:
            msg = "Entity repository is required for in-space neighborhood traversal"
            raise ValueError(msg)
        entity = self._entities.get_by_id(entity_id)
        if entity is None:
            msg = f"Entity {entity_id} not found"
            raise ValueError(msg)
        if str(entity.research_space_id) != str(research_space_id):
            msg = f"Entity {entity_id} is not in research space {research_space_id}"
            raise ValueError(msg)

        relations = self._relations.find_neighborhood(
            entity_id,
            depth=depth,
            relation_types=relation_types,
            claim_backed_only=claim_backed_only,
            limit=limit,
        )
        return [
            rel
            for rel in relations
            if str(rel.research_space_id) == str(research_space_id)
        ]

    def list_by_research_space(  # noqa: PLR0913 - mirrors repository query filters
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
        claim_backed_only: bool = True,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[KernelRelation]:
        """Paginated listing of relations in a research space."""
        return self._relations.find_by_research_space(
            research_space_id,
            relation_type=relation_type,
            curation_status=curation_status,
            validation_state=validation_state,
            source_document_id=source_document_id,
            certainty_band=certainty_band,
            node_query=node_query,
            node_ids=node_ids,
            claim_backed_only=claim_backed_only,
            limit=limit,
            offset=offset,
        )

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
        claim_backed_only: bool = True,
    ) -> int:
        """Count relations in one research space with optional filters."""
        return self._relations.count_by_research_space(
            research_space_id,
            relation_type=relation_type,
            curation_status=curation_status,
            validation_state=validation_state,
            source_document_id=source_document_id,
            certainty_band=certainty_band,
            node_query=node_query,
            node_ids=node_ids,
            claim_backed_only=claim_backed_only,
        )

    # ── Delete ────────────────────────────────────────────────────────

    def delete_relation(self, relation_id: str) -> bool:
        """Delete a relation."""
        return self._relations.delete(relation_id)

    def rollback_provenance(self, provenance_id: str) -> int:
        """Delete all relations linked to a provenance record."""
        return self._relations.delete_by_provenance(provenance_id)


__all__ = ["KernelRelationService"]
