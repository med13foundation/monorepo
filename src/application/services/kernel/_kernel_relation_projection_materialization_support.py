"""Helper types and pure functions for relation projection materialization."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    from collections.abc import Sequence

    from src.domain.entities.kernel.claim_evidence import KernelClaimEvidence
    from src.domain.entities.kernel.claim_participants import KernelClaimParticipant
    from src.domain.entities.kernel.relation_claims import KernelRelationClaim
    from src.domain.entities.kernel.relations import KernelRelation


class RelationProjectionMaterializationError(ValueError):
    """Raised when a claim cannot be materialized into a canonical relation."""


@dataclass(frozen=True)
class RelationProjectionMaterializationResult:
    """Outcome of one projection materialization or rebuild operation."""

    relation: KernelRelation | None
    rebuilt_relation_ids: tuple[str, ...] = ()
    deleted_relation_ids: tuple[str, ...] = ()
    derived_evidence_rows: int = 0


@dataclass(frozen=True)
class _ProjectionEndpoints:
    source_id: str
    source_label: str | None
    source_type: str
    relation_type: str
    target_id: str
    target_label: str | None
    target_type: str


def _participant_for_role(
    participants: list[KernelClaimParticipant],
    *,
    role: str,
) -> KernelClaimParticipant | None:
    normalized_role = role.strip().upper()
    for participant in participants:
        if participant.role == normalized_role:
            return participant
    return None


def _is_active_support_claim(claim: KernelRelationClaim) -> bool:
    return (
        claim.polarity == "SUPPORT"
        and claim.claim_status == "RESOLVED"
        and claim.persistability == "PERSISTABLE"
    )


def _claim_evidence_summary(
    *,
    claim: KernelRelationClaim,
    evidence: KernelClaimEvidence,
) -> str | None:
    metadata = evidence.metadata_payload
    if isinstance(metadata, dict):
        raw_summary = metadata.get("evidence_summary")
        if isinstance(raw_summary, str) and raw_summary.strip():
            return raw_summary.strip()[:2000]
    if isinstance(claim.claim_text, str) and claim.claim_text.strip():
        return claim.claim_text.strip()[:2000]
    return None


def _claim_evidence_tier(evidence: KernelClaimEvidence) -> str:
    metadata = evidence.metadata_payload
    if isinstance(metadata, dict):
        raw_tier = metadata.get("evidence_tier")
        if isinstance(raw_tier, str) and raw_tier.strip():
            return raw_tier.strip().upper()[:32]
    return "COMPUTATIONAL"


def _claim_evidence_provenance_id(
    evidence: KernelClaimEvidence,
) -> UUID | None:
    metadata = evidence.metadata_payload
    if isinstance(metadata, dict):
        raw_provenance_id = metadata.get("provenance_id")
        if isinstance(raw_provenance_id, str):
            normalized = raw_provenance_id.strip()
            if normalized:
                try:
                    return UUID(normalized)
                except ValueError:
                    return None
    return None


def _relation_provenance_id(
    *,
    claim: KernelRelationClaim,
    evidences: Sequence[KernelClaimEvidence],
) -> str | None:
    claim_metadata = claim.metadata_payload
    if isinstance(claim_metadata, dict):
        raw_provenance_id = claim_metadata.get("provenance_id")
        if isinstance(raw_provenance_id, str) and raw_provenance_id.strip():
            return raw_provenance_id.strip()
        supporting_provenance_ids = claim_metadata.get("supporting_provenance_ids")
        if isinstance(supporting_provenance_ids, list):
            for provenance_id in supporting_provenance_ids:
                if isinstance(provenance_id, str) and provenance_id.strip():
                    return provenance_id.strip()
    for evidence in evidences:
        provenance_id = _claim_evidence_provenance_id(evidence)
        if provenance_id is not None:
            return str(provenance_id)
    return None


def _dedupe_relation_ids(relation_ids: list[str]) -> list[str]:
    deduped: list[str] = []
    for relation_id in relation_ids:
        normalized = relation_id.strip()
        if not normalized or normalized in deduped:
            continue
        deduped.append(normalized)
    return deduped


__all__ = [
    "_ProjectionEndpoints",
    "_claim_evidence_provenance_id",
    "_claim_evidence_summary",
    "_claim_evidence_tier",
    "_dedupe_relation_ids",
    "_is_active_support_claim",
    "_participant_for_role",
    "_relation_provenance_id",
    "RelationProjectionMaterializationError",
    "RelationProjectionMaterializationResult",
]
