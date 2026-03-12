"""Kernel relation projection-lineage repository interface."""

from __future__ import annotations

from abc import ABC, abstractmethod

from src.domain.entities.kernel.relation_projection_sources import (  # noqa: TC001
    KernelRelationProjectionSource,
    RelationProjectionOrigin,
)
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
    def count_by_relation_ids(
        self,
        *,
        research_space_id: str,
        relation_ids: list[str],
    ) -> dict[str, int]:
        """Count projection-lineage rows per relation for one space."""


__all__ = [
    "KernelRelationProjectionSourceRepository",
    "RelationProjectionConstraintError",
]
