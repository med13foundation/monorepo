"""Kernel claim-evidence repository interface."""

from __future__ import annotations

from abc import ABC, abstractmethod

from src.domain.entities.kernel.claim_evidence import (  # noqa: TC001
    ClaimEvidenceSentenceConfidence,
    ClaimEvidenceSentenceSource,
    KernelClaimEvidence,
)
from src.type_definitions.common import JSONObject  # noqa: TC001


class KernelClaimEvidenceRepository(ABC):
    """Repository contract for claim_evidence CRUD operations."""

    @abstractmethod
    def create(  # noqa: PLR0913
        self,
        *,
        claim_id: str,
        source_document_id: str | None,
        agent_run_id: str | None,
        sentence: str | None,
        sentence_source: ClaimEvidenceSentenceSource | None,
        sentence_confidence: ClaimEvidenceSentenceConfidence | None,
        sentence_rationale: str | None,
        figure_reference: str | None,
        table_reference: str | None,
        confidence: float,
        source_document_ref: str | None = None,
        metadata: JSONObject | None = None,
    ) -> KernelClaimEvidence:
        """Create one claim evidence row."""

    @abstractmethod
    def find_by_claim_id(self, claim_id: str) -> list[KernelClaimEvidence]:
        """List evidence rows for a claim ordered by recency."""

    @abstractmethod
    def find_by_claim_ids(
        self,
        claim_ids: list[str],
    ) -> dict[str, list[KernelClaimEvidence]]:
        """List evidence rows for multiple claims keyed by claim ID."""

    @abstractmethod
    def get_preferred_for_claim(self, claim_id: str) -> KernelClaimEvidence | None:
        """Return preferred evidence row for claim resolution usage."""


__all__ = ["KernelClaimEvidenceRepository"]
