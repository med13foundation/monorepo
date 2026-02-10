"""
Kernel relation application service.

Creates graph edges with constraint validation, manages
curation lifecycle, and provides graph traversal.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import datetime

    from src.domain.entities.kernel.relations import KernelRelation
    from src.domain.repositories.kernel.dictionary_repository import (
        DictionaryRepository,
    )
    from src.domain.repositories.kernel.entity_repository import (
        KernelEntityRepository,
    )
    from src.domain.repositories.kernel.relation_repository import (
        KernelRelationRepository,
    )

logger = logging.getLogger(__name__)


class KernelRelationService:
    """
    Application service for kernel relations (graph edges).

    Validates triples against relation constraints before creation
    and manages the curation lifecycle.
    """

    def __init__(
        self,
        relation_repo: KernelRelationRepository,
        entity_repo: KernelEntityRepository,
        dictionary_repo: DictionaryRepository,
    ) -> None:
        self._relations = relation_repo
        self._entities = entity_repo
        self._dictionary = dictionary_repo

    # ── Create ────────────────────────────────────────────────────────

    def create_relation(  # noqa: PLR0913
        self,
        *,
        research_space_id: str,
        source_id: str,
        relation_type: str,
        target_id: str,
        confidence: float = 0.5,
        evidence_summary: str | None = None,
        evidence_tier: str | None = None,
        provenance_id: str | None = None,
    ) -> KernelRelation:
        """
        Create a relation with constraint validation.

        1. Verify source and target entities exist
        2. Check relation constraint allows the triple
        3. Check evidence requirement
        4. Create the relation
        """
        # 1. Verify entities exist
        source = self._entities.get_by_id(source_id)
        if source is None:
            msg = f"Source entity {source_id} not found"
            raise ValueError(msg)

        target = self._entities.get_by_id(target_id)
        if target is None:
            msg = f"Target entity {target_id} not found"
            raise ValueError(msg)

        # 1b. Enforce research-space isolation for graph edges
        if str(source.research_space_id) != str(research_space_id):
            msg = f"Source entity {source_id} is not in research space {research_space_id}"
            raise ValueError(msg)
        if str(target.research_space_id) != str(research_space_id):
            msg = f"Target entity {target_id} is not in research space {research_space_id}"
            raise ValueError(msg)

        # 2. Check triple is allowed
        if not self._dictionary.is_triple_allowed(
            source.entity_type,
            relation_type,
            target.entity_type,
        ):
            msg = (
                f"Triple ({source.entity_type}, {relation_type}, "
                f"{target.entity_type}) is not allowed by constraints"
            )
            raise ValueError(msg)

        # 3. Check evidence requirement
        if (
            self._dictionary.requires_evidence(
                source.entity_type,
                relation_type,
                target.entity_type,
            )
            and not evidence_summary
        ):
            logger.warning(
                "Creating relation %s without evidence (required by constraints)",
                relation_type,
            )

        return self._relations.create(
            research_space_id=research_space_id,
            source_id=source_id,
            relation_type=relation_type,
            target_id=target_id,
            confidence=confidence,
            evidence_summary=evidence_summary,
            evidence_tier=evidence_tier,
            provenance_id=provenance_id,
        )

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
        return self._relations.update_curation(
            relation_id,
            curation_status=curation_status,
            reviewed_by=reviewed_by,
            reviewed_at=reviewed_at,
        )

    # ── Read operations ───────────────────────────────────────────────

    def get_relation(self, relation_id: str) -> KernelRelation | None:
        """Retrieve a single relation."""
        return self._relations.get_by_id(relation_id)

    def get_neighborhood(
        self,
        entity_id: str,
        *,
        depth: int = 1,
        relation_types: list[str] | None = None,
    ) -> list[KernelRelation]:
        """Graph traversal around an entity."""
        return self._relations.find_neighborhood(
            entity_id,
            depth=depth,
            relation_types=relation_types,
        )

    def get_neighborhood_in_space(
        self,
        research_space_id: str,
        entity_id: str,
        *,
        depth: int = 1,
        relation_types: list[str] | None = None,
    ) -> list[KernelRelation]:
        """
        Graph traversal around an entity, restricted to a research space.

        This protects against cross-space leakage if invalid relations exist.
        """
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
        )
        return [
            rel
            for rel in relations
            if str(rel.research_space_id) == str(research_space_id)
        ]

    def list_by_research_space(
        self,
        research_space_id: str,
        *,
        relation_type: str | None = None,
        curation_status: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[KernelRelation]:
        """Paginated listing of relations in a research space."""
        return self._relations.find_by_research_space(
            research_space_id,
            relation_type=relation_type,
            curation_status=curation_status,
            limit=limit,
            offset=offset,
        )

    # ── Delete ────────────────────────────────────────────────────────

    def delete_relation(self, relation_id: str) -> bool:
        """Delete a relation."""
        return self._relations.delete(relation_id)

    def rollback_provenance(self, provenance_id: str) -> int:
        """Delete all relations linked to a provenance record."""
        return self._relations.delete_by_provenance(provenance_id)


__all__ = ["KernelRelationService"]
