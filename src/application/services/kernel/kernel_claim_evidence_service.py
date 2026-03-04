"""Kernel claim-evidence application service."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.domain.entities.kernel.claim_evidence import KernelClaimEvidence
    from src.domain.repositories.kernel.claim_evidence_repository import (
        KernelClaimEvidenceRepository,
    )


class KernelClaimEvidenceService:
    """Application service for claim evidence read/write workflows."""

    def __init__(self, claim_evidence_repo: KernelClaimEvidenceRepository) -> None:
        self._claim_evidence = claim_evidence_repo

    def list_for_claim(self, claim_id: str) -> list[KernelClaimEvidence]:
        """List evidence rows for one claim by recency."""
        return self._claim_evidence.find_by_claim_id(claim_id)

    def get_preferred_for_claim(self, claim_id: str) -> KernelClaimEvidence | None:
        """Return preferred evidence row for claim-to-relation resolution."""
        return self._claim_evidence.get_preferred_for_claim(claim_id)


__all__ = ["KernelClaimEvidenceService"]
