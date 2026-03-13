"""Kernel claim-relation application service."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.domain.entities.kernel.claim_relations import (
        ClaimRelationReviewStatus,
        ClaimRelationType,
        KernelClaimRelation,
    )
    from src.domain.repositories.kernel.claim_relation_repository import (
        KernelClaimRelationRepository,
    )
    from src.type_definitions.common import JSONObject


class KernelClaimRelationService:
    """Application service for claim-to-claim relation graph workflows."""

    def __init__(self, claim_relation_repo: KernelClaimRelationRepository) -> None:
        self._claim_relations = claim_relation_repo

    def create_claim_relation(  # noqa: PLR0913
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
        source_document_ref: str | None = None,
        metadata: JSONObject | None = None,
    ) -> KernelClaimRelation:
        """Create one claim relation row."""
        return self._claim_relations.create(
            research_space_id=research_space_id,
            source_claim_id=source_claim_id,
            target_claim_id=target_claim_id,
            relation_type=relation_type,
            agent_run_id=agent_run_id,
            source_document_id=source_document_id,
            source_document_ref=source_document_ref,
            confidence=confidence,
            review_status=review_status,
            evidence_summary=evidence_summary,
            metadata=metadata,
        )

    def get_claim_relation(self, relation_id: str) -> KernelClaimRelation | None:
        """Fetch one claim relation by ID."""
        return self._claim_relations.get_by_id(relation_id)

    def list_by_claim_ids(
        self,
        research_space_id: str,
        claim_ids: list[str],
        *,
        limit: int | None = None,
    ) -> list[KernelClaimRelation]:
        """List claim relations touching any of the provided claim IDs."""
        return self._claim_relations.find_by_claim_ids(
            research_space_id,
            claim_ids,
            limit=limit,
        )

    def list_by_research_space(  # noqa: PLR0913
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
        return self._claim_relations.find_by_research_space(
            research_space_id,
            relation_type=relation_type,
            review_status=review_status,
            source_claim_id=source_claim_id,
            target_claim_id=target_claim_id,
            claim_id=claim_id,
            limit=limit,
            offset=offset,
        )

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
        """Count claim relations in one research space."""
        return self._claim_relations.count_by_research_space(
            research_space_id,
            relation_type=relation_type,
            review_status=review_status,
            source_claim_id=source_claim_id,
            target_claim_id=target_claim_id,
            claim_id=claim_id,
        )

    def update_review_status(
        self,
        relation_id: str,
        *,
        review_status: ClaimRelationReviewStatus,
    ) -> KernelClaimRelation:
        """Update review status for one claim relation row."""
        return self._claim_relations.update_review_status(
            relation_id,
            review_status=review_status,
        )


__all__ = ["KernelClaimRelationService"]
