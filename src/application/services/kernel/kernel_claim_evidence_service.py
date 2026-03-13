"""Kernel claim-evidence application service."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.domain.entities.kernel.claim_evidence import (
        ClaimEvidenceSentenceConfidence,
        ClaimEvidenceSentenceSource,
        KernelClaimEvidence,
    )
    from src.domain.repositories.kernel.claim_evidence_repository import (
        KernelClaimEvidenceRepository,
    )
    from src.type_definitions.common import JSONObject


class KernelClaimEvidenceService:
    """Application service for claim evidence read/write workflows."""

    def __init__(self, claim_evidence_repo: KernelClaimEvidenceRepository) -> None:
        self._claim_evidence = claim_evidence_repo

    def list_for_claim(self, claim_id: str) -> list[KernelClaimEvidence]:
        """List evidence rows for one claim by recency."""
        return self._claim_evidence.find_by_claim_id(claim_id)

    def create_evidence(  # noqa: PLR0913
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
        return self._claim_evidence.create(
            claim_id=claim_id,
            source_document_id=source_document_id,
            source_document_ref=source_document_ref,
            agent_run_id=agent_run_id,
            sentence=sentence,
            sentence_source=sentence_source,
            sentence_confidence=sentence_confidence,
            sentence_rationale=sentence_rationale,
            figure_reference=figure_reference,
            table_reference=table_reference,
            confidence=confidence,
            metadata=metadata,
        )

    def list_for_claim_ids(
        self,
        claim_ids: list[str],
    ) -> dict[str, list[KernelClaimEvidence]]:
        """List evidence rows for multiple claims keyed by claim ID."""
        return self._claim_evidence.find_by_claim_ids(claim_ids)

    def get_preferred_for_claim(self, claim_id: str) -> KernelClaimEvidence | None:
        """Return preferred evidence row for claim-to-relation resolution."""
        return self._claim_evidence.get_preferred_for_claim(claim_id)


__all__ = ["KernelClaimEvidenceService"]
