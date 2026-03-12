"""Support types and helpers for graph view assembly."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal
from uuid import UUID

if TYPE_CHECKING:
    from src.application.services.kernel.kernel_claim_evidence_service import (
        KernelClaimEvidenceService,
    )
    from src.application.services.kernel.kernel_claim_participant_service import (
        KernelClaimParticipantService,
    )
    from src.application.services.kernel.kernel_claim_relation_service import (
        KernelClaimRelationService,
    )
    from src.application.services.kernel.kernel_entity_service import (
        KernelEntityService,
    )
    from src.application.services.kernel.kernel_relation_claim_service import (
        KernelRelationClaimService,
    )
    from src.application.services.kernel.kernel_relation_service import (
        KernelRelationService,
    )
    from src.domain.entities.kernel.claim_evidence import KernelClaimEvidence
    from src.domain.entities.kernel.claim_participants import KernelClaimParticipant
    from src.domain.entities.kernel.claim_relations import KernelClaimRelation
    from src.domain.entities.kernel.entities import KernelEntity
    from src.domain.entities.kernel.relation_claims import KernelRelationClaim
    from src.domain.entities.kernel.relations import KernelRelation
    from src.domain.entities.source_document import SourceDocument
    from src.domain.repositories.source_document_repository import (
        SourceDocumentRepository,
    )


GraphDomainViewType = Literal["gene", "variant", "phenotype", "paper", "claim"]
ENTITY_VIEW_TYPES: dict[GraphDomainViewType, str] = {
    "gene": "GENE",
    "variant": "VARIANT",
    "phenotype": "PHENOTYPE",
}
MECHANISM_RELATION_TYPES = frozenset(
    {
        "CAUSES",
        "UPSTREAM_OF",
        "DOWNSTREAM_OF",
        "REFINES",
        "SUPPORTS",
        "GENERALIZES",
        "INSTANCE_OF",
    },
)


class KernelGraphViewError(Exception):
    """Base exception for graph view failures."""


class KernelGraphViewNotFoundError(KernelGraphViewError):
    """Raised when a requested graph resource does not exist."""


class KernelGraphViewValidationError(KernelGraphViewError):
    """Raised when a graph view request is invalid."""


@dataclass(frozen=True)
class KernelGraphViewServiceDependencies:
    """Typed dependency bundle for graph view assembly."""

    entity_service: KernelEntityService
    relation_service: KernelRelationService
    relation_claim_service: KernelRelationClaimService
    claim_participant_service: KernelClaimParticipantService
    claim_relation_service: KernelClaimRelationService
    claim_evidence_service: KernelClaimEvidenceService
    source_document_repository: SourceDocumentRepository


@dataclass(frozen=True)
class KernelGraphDomainView:
    """Assembled graph view for one domain resource."""

    view_type: GraphDomainViewType
    resource_id: str
    entity: KernelEntity | None
    claim: KernelRelationClaim | None
    paper: SourceDocument | None
    canonical_relations: tuple[KernelRelation, ...]
    claims: tuple[KernelRelationClaim, ...]
    claim_relations: tuple[KernelClaimRelation, ...]
    participants: tuple[KernelClaimParticipant, ...]
    evidence: tuple[KernelClaimEvidence, ...]


@dataclass(frozen=True)
class KernelClaimMechanismChain:
    """Traversable mechanism-style chain rooted at one claim."""

    root_claim: KernelRelationClaim
    max_depth: int
    canonical_relations: tuple[KernelRelation, ...]
    claims: tuple[KernelRelationClaim, ...]
    claim_relations: tuple[KernelClaimRelation, ...]
    participants: tuple[KernelClaimParticipant, ...]
    evidence: tuple[KernelClaimEvidence, ...]


@dataclass(frozen=True)
class ClaimBundle:
    """Bundle of claims plus the attached overlay payloads."""

    claims: tuple[KernelRelationClaim, ...]
    claim_relations: tuple[KernelClaimRelation, ...]
    participants: tuple[KernelClaimParticipant, ...]
    evidence: tuple[KernelClaimEvidence, ...]
    canonical_relations: tuple[KernelRelation, ...]


def normalize_ids(ids: list[str]) -> list[str]:
    """Normalize UUID strings and preserve insertion order."""
    seen: set[str] = set()
    normalized: list[str] = []
    for value in ids:
        try:
            normalized_id = str(UUID(str(value)))
        except ValueError:
            continue
        if normalized_id in seen:
            continue
        seen.add(normalized_id)
        normalized.append(normalized_id)
    return normalized


def sort_claims(
    claims: list[KernelRelationClaim] | None,
) -> tuple[KernelRelationClaim, ...]:
    """Sort claims by recency."""
    if claims is None:
        return ()
    return tuple(sorted(claims, key=lambda item: item.created_at, reverse=True))


def sort_claim_relations(
    claim_relations: list[KernelClaimRelation] | None,
) -> tuple[KernelClaimRelation, ...]:
    """Sort claim-to-claim edges by recency."""
    if claim_relations is None:
        return ()
    return tuple(
        sorted(claim_relations, key=lambda item: item.created_at, reverse=True),
    )


def flatten_participants(
    claim_ids: list[str],
    participants_by_claim_id: dict[str, list[KernelClaimParticipant]],
) -> list[KernelClaimParticipant]:
    """Flatten participant rows in claim order."""
    participants: list[KernelClaimParticipant] = []
    for claim_id in claim_ids:
        participants.extend(participants_by_claim_id.get(claim_id, []))
    return sorted(
        participants,
        key=lambda item: (str(item.claim_id), item.position or 0, item.created_at),
    )


def flatten_evidence(
    claim_ids: list[str],
    evidence_by_claim_id: dict[str, list[KernelClaimEvidence]],
) -> list[KernelClaimEvidence]:
    """Flatten evidence rows in claim order."""
    evidence: list[KernelClaimEvidence] = []
    for claim_id in claim_ids:
        evidence.extend(evidence_by_claim_id.get(claim_id, []))
    return sorted(
        evidence,
        key=lambda item: (str(item.claim_id), item.created_at),
    )


def dedupe_relations(relations: list[KernelRelation]) -> list[KernelRelation]:
    """Deduplicate relations by ID and sort by recency."""
    deduped: dict[str, KernelRelation] = {}
    for relation in relations:
        deduped[str(relation.id)] = relation
    return sorted(
        deduped.values(),
        key=lambda item: item.updated_at,
        reverse=True,
    )


__all__ = [
    "ClaimBundle",
    "ENTITY_VIEW_TYPES",
    "GraphDomainViewType",
    "KernelClaimMechanismChain",
    "KernelGraphDomainView",
    "KernelGraphViewError",
    "KernelGraphViewNotFoundError",
    "KernelGraphViewServiceDependencies",
    "KernelGraphViewValidationError",
    "MECHANISM_RELATION_TYPES",
    "dedupe_relations",
    "flatten_evidence",
    "flatten_participants",
    "normalize_ids",
    "sort_claim_relations",
    "sort_claims",
]
