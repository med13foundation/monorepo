"""Kernel relation projection-lineage repository interface."""

from __future__ import annotations

from abc import ABC, abstractmethod

from src.domain.entities.kernel.relation_projection_sources import (  # noqa: TC001
    KernelRelationProjectionSource,
    RelationProjectionOrigin,
)
from src.domain.entities.kernel.relations import KernelRelation  # noqa: TC001
from src.type_definitions.common import JSONObject  # noqa: TC001


class RelationProjectionConstraintError(Exception):
    """Raised when projection-lineage writes violate storage constraints."""


class KernelRelationProjectionSourceRepository(ABC):
    """Repository contract for canonical relation projection lineage."""

    @abstractmethod
    def create(  # noqa: PLR0913
        self,
        *,
        research_space_id: str,
        relation_id: str,
        claim_id: str,
        projection_origin: RelationProjectionOrigin,
        source_document_id: str | None,
        agent_run_id: str | None,
        source_document_ref: str | None = None,
        metadata: JSONObject | None = None,
    ) -> KernelRelationProjectionSource:
        """Create or return one projection-lineage row."""

    @abstractmethod
    def find_by_relation_id(
        self,
        relation_id: str,
    ) -> list[KernelRelationProjectionSource]:
        """List claim lineage rows for one canonical relation."""

    @abstractmethod
    def find_by_claim_id(
        self,
        *,
        research_space_id: str,
        claim_id: str,
    ) -> list[KernelRelationProjectionSource]:
        """List projection-lineage rows for one claim."""

    @abstractmethod
    def count_by_relation_ids(
        self,
        *,
        research_space_id: str,
        relation_ids: list[str],
    ) -> dict[str, int]:
        """Count projection-lineage rows per relation for one space."""

    @abstractmethod
    def has_projection_for_relation(
        self,
        *,
        research_space_id: str,
        relation_id: str,
    ) -> bool:
        """Return whether one canonical relation has at least one lineage row."""

    @abstractmethod
    def list_orphan_relations(
        self,
        *,
        research_space_id: str | None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[KernelRelation]:
        """List canonical relations that have no projection-lineage row."""

    @abstractmethod
    def count_orphan_relations(
        self,
        *,
        research_space_id: str | None,
    ) -> int:
        """Count canonical relations that have no projection-lineage row."""

    @abstractmethod
    def delete_by_claim_id(
        self,
        *,
        research_space_id: str,
        claim_id: str,
    ) -> list[str]:
        """Delete projection-lineage rows for one claim and return relation IDs."""

    @abstractmethod
    def delete_projection_source(
        self,
        *,
        research_space_id: str,
        relation_id: str,
        claim_id: str,
    ) -> bool:
        """Delete one claim/relation projection-lineage row."""


__all__ = [
    "KernelRelationProjectionSourceRepository",
    "RelationProjectionConstraintError",
]
