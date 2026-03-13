"""Kernel relation-claim application service."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from src.domain.entities.kernel.relation_claims import (
        KernelRelationClaim,
        KernelRelationConflictSummary,
        RelationClaimPersistability,
        RelationClaimPolarity,
        RelationClaimStatus,
        RelationClaimValidationState,
    )
    from src.domain.repositories.kernel.relation_claim_repository import (
        CertaintyBand,
        KernelRelationClaimRepository,
    )
    from src.type_definitions.common import JSONObject


class KernelRelationClaimService:
    """Application service for relation-claim curation workflows."""

    def __init__(self, relation_claim_repo: KernelRelationClaimRepository) -> None:
        self._claims = relation_claim_repo

    def get_claim(self, claim_id: str) -> KernelRelationClaim | None:
        """Fetch one relation claim by ID."""
        return self._claims.get_by_id(claim_id)

    def list_claims_by_ids(self, claim_ids: list[str]) -> list[KernelRelationClaim]:
        """Fetch multiple relation claims by IDs."""
        return self._claims.list_by_ids(claim_ids)

    def list_by_linked_relation_ids(
        self,
        *,
        research_space_id: str,
        linked_relation_ids: list[str],
    ) -> list[KernelRelationClaim]:
        """List claims linked to one or more canonical relations."""
        return self._claims.find_by_linked_relation_ids(
            research_space_id=research_space_id,
            linked_relation_ids=linked_relation_ids,
        )

    def list_by_research_space(  # noqa: PLR0913
        self,
        research_space_id: str,
        *,
        claim_status: RelationClaimStatus | None = None,
        validation_state: RelationClaimValidationState | None = None,
        persistability: RelationClaimPersistability | None = None,
        polarity: RelationClaimPolarity | None = None,
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
            polarity=polarity,
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
        polarity: RelationClaimPolarity | None = None,
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
            polarity=polarity,
            source_document_id=source_document_id,
            relation_type=relation_type,
            linked_relation_id=linked_relation_id,
            certainty_band=certainty_band,
        )

    def list_conflicts_by_research_space(
        self,
        research_space_id: str,
        *,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[KernelRelationConflictSummary]:
        """List conflict summaries for one research space."""
        return self._claims.find_conflicts_by_research_space(
            research_space_id,
            limit=limit,
            offset=offset,
        )

    def count_conflicts_by_research_space(self, research_space_id: str) -> int:
        """Count conflict summaries for one research space."""
        return self._claims.count_conflicts_by_research_space(research_space_id)

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

    def clear_claim_relation_link(
        self,
        claim_id: str,
    ) -> KernelRelationClaim:
        """Clear the linked canonical relation pointer for one claim."""
        return self._claims.clear_relation_link(claim_id)

    def set_system_status(
        self,
        claim_id: str,
        *,
        claim_status: RelationClaimStatus,
    ) -> KernelRelationClaim:
        """Set claim status via automated pipeline action."""
        return self._claims.set_system_status(
            claim_id,
            claim_status=claim_status,
        )

    def create_claim(  # noqa: PLR0913
        self,
        *,
        research_space_id: str,
        source_document_id: str | None,
        agent_run_id: str | None,
        source_type: str,
        relation_type: str,
        target_type: str,
        source_label: str | None,
        target_label: str | None,
        confidence: float,
        validation_state: RelationClaimValidationState,
        validation_reason: str | None,
        persistability: RelationClaimPersistability,
        claim_status: RelationClaimStatus,
        polarity: RelationClaimPolarity,
        claim_text: str | None,
        claim_section: str | None,
        linked_relation_id: str | None = None,
        source_document_ref: str | None = None,
        metadata: JSONObject | None = None,
    ) -> KernelRelationClaim:
        """Create one generic relation claim row."""
        return self._claims.create(
            research_space_id=research_space_id,
            source_document_id=source_document_id,
            source_document_ref=source_document_ref,
            agent_run_id=agent_run_id,
            source_type=source_type,
            relation_type=relation_type,
            target_type=target_type,
            source_label=source_label,
            target_label=target_label,
            confidence=confidence,
            validation_state=validation_state,
            validation_reason=validation_reason,
            persistability=persistability,
            claim_status=claim_status,
            polarity=polarity,
            claim_text=claim_text,
            claim_section=claim_section,
            linked_relation_id=linked_relation_id,
            metadata=metadata,
        )

    def create_hypothesis_claim(  # noqa: PLR0913
        self,
        *,
        research_space_id: str,
        source_type: str,
        relation_type: str,
        target_type: str,
        source_label: str | None,
        target_label: str | None,
        confidence: float,
        validation_state: RelationClaimValidationState,
        validation_reason: str | None,
        persistability: RelationClaimPersistability,
        claim_text: str | None,
        metadata: JSONObject | None = None,
        source_document_id: str | None = None,
        source_document_ref: str | None = None,
        agent_run_id: str | None = None,
        claim_status: RelationClaimStatus = "OPEN",
    ) -> KernelRelationClaim:
        """Create one hypothesis claim in the relation-claim ledger."""
        return self._claims.create(
            research_space_id=research_space_id,
            source_document_id=source_document_id,
            source_document_ref=source_document_ref,
            agent_run_id=agent_run_id,
            source_type=source_type,
            relation_type=relation_type,
            target_type=target_type,
            source_label=source_label,
            target_label=target_label,
            confidence=confidence,
            validation_state=validation_state,
            validation_reason=validation_reason,
            persistability=persistability,
            claim_status=claim_status,
            polarity="HYPOTHESIS",
            claim_text=claim_text,
            claim_section=None,
            linked_relation_id=None,
            metadata=metadata,
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
