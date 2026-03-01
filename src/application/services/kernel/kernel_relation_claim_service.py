"""Kernel relation-claim application service."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from src.domain.entities.kernel.relation_claims import (
        KernelRelationClaim,
        RelationClaimPersistability,
        RelationClaimStatus,
        RelationClaimValidationState,
    )
    from src.domain.repositories.kernel.relation_claim_repository import (
        CertaintyBand,
        KernelRelationClaimRepository,
    )


class KernelRelationClaimService:
    """Application service for relation-claim curation workflows."""

    def __init__(self, relation_claim_repo: KernelRelationClaimRepository) -> None:
        self._claims = relation_claim_repo

    def get_claim(self, claim_id: str) -> KernelRelationClaim | None:
        """Fetch one relation claim by ID."""
        return self._claims.get_by_id(claim_id)

    def list_by_research_space(  # noqa: PLR0913
        self,
        research_space_id: str,
        *,
        claim_status: RelationClaimStatus | None = None,
        validation_state: RelationClaimValidationState | None = None,
        persistability: RelationClaimPersistability | None = None,
        source_document_id: str | None = None,
        relation_type: str | None = None,
        linked_relation_id: str | None = None,
        certainty_band: CertaintyBand | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[KernelRelationClaim]:
        """List claims for one research space."""
        return self._claims.find_by_research_space(
            research_space_id,
            claim_status=claim_status,
            validation_state=validation_state,
            persistability=persistability,
            source_document_id=source_document_id,
            relation_type=relation_type,
            linked_relation_id=linked_relation_id,
            certainty_band=certainty_band,
            limit=limit,
            offset=offset,
        )

    def count_by_research_space(  # noqa: PLR0913
        self,
        research_space_id: str,
        *,
        claim_status: RelationClaimStatus | None = None,
        validation_state: RelationClaimValidationState | None = None,
        persistability: RelationClaimPersistability | None = None,
        source_document_id: str | None = None,
        relation_type: str | None = None,
        linked_relation_id: str | None = None,
        certainty_band: CertaintyBand | None = None,
    ) -> int:
        """Count claims in one research space."""
        return self._claims.count_by_research_space(
            research_space_id,
            claim_status=claim_status,
            validation_state=validation_state,
            persistability=persistability,
            source_document_id=source_document_id,
            relation_type=relation_type,
            linked_relation_id=linked_relation_id,
            certainty_band=certainty_band,
        )

    def update_claim_status(
        self,
        claim_id: str,
        *,
        claim_status: RelationClaimStatus,
        triaged_by: str,
    ) -> KernelRelationClaim:
        """Update one relation-claim triage status."""
        return self._claims.update_triage_status(
            claim_id,
            claim_status=claim_status,
            triaged_by=triaged_by,
        )

    def link_claim_to_relation(
        self,
        claim_id: str,
        *,
        linked_relation_id: str,
    ) -> KernelRelationClaim:
        """Attach one claim to a canonical relation."""
        return self._claims.link_relation(
            claim_id,
            linked_relation_id=linked_relation_id,
        )

    @staticmethod
    def normalize_status_alias(
        value: str,
    ) -> Literal["OPEN", "NEEDS_MAPPING", "REJECTED", "RESOLVED"]:
        """Normalize user-provided status strings."""
        normalized = value.strip().upper()
        if normalized == "OPEN":
            return "OPEN"
        if normalized == "NEEDS_MAPPING":
            return "NEEDS_MAPPING"
        if normalized == "REJECTED":
            return "REJECTED"
        if normalized == "RESOLVED":
            return "RESOLVED"
        msg = f"Unsupported claim_status '{value}'"
        raise ValueError(msg)


__all__ = ["KernelRelationClaimService"]
