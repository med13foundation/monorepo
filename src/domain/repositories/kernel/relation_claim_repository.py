"""Kernel relation-claim repository interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Literal

from src.domain.entities.kernel.relation_claims import (
    KernelRelationClaim,  # noqa: TC001
    RelationClaimPersistability,  # noqa: TC001
    RelationClaimStatus,  # noqa: TC001
    RelationClaimValidationState,  # noqa: TC001
)
from src.type_definitions.common import JSONObject  # noqa: TC001

CertaintyBand = Literal["HIGH", "MEDIUM", "LOW"]


class KernelRelationClaimRepository(ABC):
    """Repository contract for extracted relation claim ledger rows."""

    @abstractmethod
    def create(  # noqa: PLR0913
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
        claim_status: RelationClaimStatus = "OPEN",
        linked_relation_id: str | None = None,
        metadata: JSONObject | None = None,
    ) -> KernelRelationClaim:
        """Create one relation-claim row."""

    @abstractmethod
    def get_by_id(self, claim_id: str) -> KernelRelationClaim | None:
        """Fetch one claim by ID."""

    @abstractmethod
    def find_by_research_space(  # noqa: PLR0913
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
        """List claims in one space with optional filters."""

    @abstractmethod
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
        """Count claims in one space with optional filters."""

    @abstractmethod
    def update_triage_status(
        self,
        claim_id: str,
        *,
        claim_status: RelationClaimStatus,
        triaged_by: str,
    ) -> KernelRelationClaim:
        """Update triage status for one claim."""

    @abstractmethod
    def link_relation(
        self,
        claim_id: str,
        *,
        linked_relation_id: str,
    ) -> KernelRelationClaim:
        """Attach a canonical relation ID to an existing claim."""


__all__ = ["CertaintyBand", "KernelRelationClaimRepository"]
