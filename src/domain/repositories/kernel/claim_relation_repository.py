"""Kernel claim-relation repository interface."""

from __future__ import annotations

from abc import ABC, abstractmethod

from src.domain.entities.kernel.claim_relations import (  # noqa: TC001
    ClaimRelationReviewStatus,
    ClaimRelationType,
    KernelClaimRelation,
)
from src.type_definitions.common import JSONObject  # noqa: TC001


class ClaimRelationConstraintError(Exception):
    """Raised when claim-relation writes violate storage constraints."""


class KernelClaimRelationRepository(ABC):
    """Repository contract for claim-to-claim relation operations."""

    @abstractmethod
    def create(  # noqa: PLR0913
        self,
        *,
        research_space_id: str,
        source_claim_id: str,
        target_claim_id: str,
        relation_type: ClaimRelationType,
        agent_run_id: str | None,
        source_document_id: str | None,
        confidence: float,
        review_status: ClaimRelationReviewStatus,
        evidence_summary: str | None,
        metadata: JSONObject | None = None,
    ) -> KernelClaimRelation:
        """Create one claim relation row."""

    @abstractmethod
    def get_by_id(self, relation_id: str) -> KernelClaimRelation | None:
        """Fetch one claim relation by ID."""

    @abstractmethod
    def find_by_research_space(  # noqa: PLR0913
        self,
        research_space_id: str,
        *,
        relation_type: ClaimRelationType | None = None,
        review_status: ClaimRelationReviewStatus | None = None,
        source_claim_id: str | None = None,
        target_claim_id: str | None = None,
        claim_id: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[KernelClaimRelation]:
        """List claim relations in one research space."""

    @abstractmethod
    def count_by_research_space(  # noqa: PLR0913
        self,
        research_space_id: str,
        *,
        relation_type: ClaimRelationType | None = None,
        review_status: ClaimRelationReviewStatus | None = None,
        source_claim_id: str | None = None,
        target_claim_id: str | None = None,
        claim_id: str | None = None,
    ) -> int:
        """Count claim relations in one research space with optional filters."""

    @abstractmethod
    def update_review_status(
        self,
        relation_id: str,
        *,
        review_status: ClaimRelationReviewStatus,
    ) -> KernelClaimRelation:
        """Update review status for one claim relation row."""


__all__ = ["ClaimRelationConstraintError", "KernelClaimRelationRepository"]
