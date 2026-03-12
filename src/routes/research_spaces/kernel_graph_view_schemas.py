"""Schemas for graph domain views and mechanism chains."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from src.application.services.kernel import (
    KernelClaimMechanismChain,
    KernelGraphDomainView,
)
from src.domain.entities.source_document import SourceDocument
from src.routes.research_spaces.claim_graph_schemas import (
    ClaimParticipantResponse,
    ClaimRelationResponse,
)
from src.routes.research_spaces.kernel_schemas import (
    KernelClaimEvidenceResponse,
    KernelEntityResponse,
    KernelRelationClaimResponse,
    KernelRelationResponse,
)
from src.type_definitions.common import JSONObject


class KernelSourceDocumentResponse(BaseModel):
    """Response model for one source document in graph views."""

    model_config = ConfigDict(strict=True)

    id: UUID
    research_space_id: UUID | None
    source_id: UUID
    external_record_id: str
    source_type: str
    document_format: str
    enrichment_status: str
    extraction_status: str
    metadata: JSONObject
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, model: SourceDocument) -> KernelSourceDocumentResponse:
        return cls(
            id=model.id,
            research_space_id=model.research_space_id,
            source_id=model.source_id,
            external_record_id=model.external_record_id,
            source_type=model.source_type.value,
            document_format=model.document_format.value,
            enrichment_status=model.enrichment_status.value,
            extraction_status=model.extraction_status.value,
            metadata=dict(model.metadata),
            created_at=model.created_at,
            updated_at=model.updated_at,
        )


class KernelGraphViewCountsResponse(BaseModel):
    """Count summary for one graph view payload."""

    model_config = ConfigDict(strict=True)

    canonical_relations: int
    claims: int
    claim_relations: int
    participants: int
    evidence: int


class KernelGraphDomainViewResponse(BaseModel):
    """Response payload for one graph domain view."""

    model_config = ConfigDict(strict=True)

    view_type: str
    resource_id: UUID
    entity: KernelEntityResponse | None
    claim: KernelRelationClaimResponse | None
    paper: KernelSourceDocumentResponse | None
    canonical_relations: list[KernelRelationResponse]
    claims: list[KernelRelationClaimResponse]
    claim_relations: list[ClaimRelationResponse]
    participants: list[ClaimParticipantResponse]
    evidence: list[KernelClaimEvidenceResponse]
    counts: KernelGraphViewCountsResponse

    @classmethod
    def from_domain_view(
        cls,
        view: KernelGraphDomainView,
    ) -> KernelGraphDomainViewResponse:
        canonical_relations = [
            KernelRelationResponse.from_model(item) for item in view.canonical_relations
        ]
        claims = [KernelRelationClaimResponse.from_model(item) for item in view.claims]
        claim_relations = [
            ClaimRelationResponse.from_model(item) for item in view.claim_relations
        ]
        participants = [
            ClaimParticipantResponse.from_model(item) for item in view.participants
        ]
        evidence = [
            KernelClaimEvidenceResponse.from_model(item) for item in view.evidence
        ]
        return cls(
            view_type=view.view_type,
            resource_id=UUID(view.resource_id),
            entity=(
                KernelEntityResponse.from_model(view.entity)
                if view.entity is not None
                else None
            ),
            claim=(
                KernelRelationClaimResponse.from_model(view.claim)
                if view.claim is not None
                else None
            ),
            paper=(
                KernelSourceDocumentResponse.from_model(view.paper)
                if view.paper is not None
                else None
            ),
            canonical_relations=canonical_relations,
            claims=claims,
            claim_relations=claim_relations,
            participants=participants,
            evidence=evidence,
            counts=KernelGraphViewCountsResponse(
                canonical_relations=len(canonical_relations),
                claims=len(claims),
                claim_relations=len(claim_relations),
                participants=len(participants),
                evidence=len(evidence),
            ),
        )


class KernelClaimMechanismChainResponse(BaseModel):
    """Response payload for one claim-rooted mechanism chain."""

    model_config = ConfigDict(strict=True)

    root_claim: KernelRelationClaimResponse
    max_depth: int
    canonical_relations: list[KernelRelationResponse]
    claims: list[KernelRelationClaimResponse]
    claim_relations: list[ClaimRelationResponse]
    participants: list[ClaimParticipantResponse]
    evidence: list[KernelClaimEvidenceResponse]
    counts: KernelGraphViewCountsResponse

    @classmethod
    def from_chain(
        cls,
        chain: KernelClaimMechanismChain,
    ) -> KernelClaimMechanismChainResponse:
        canonical_relations = [
            KernelRelationResponse.from_model(item)
            for item in chain.canonical_relations
        ]
        claims = [KernelRelationClaimResponse.from_model(item) for item in chain.claims]
        claim_relations = [
            ClaimRelationResponse.from_model(item) for item in chain.claim_relations
        ]
        participants = [
            ClaimParticipantResponse.from_model(item) for item in chain.participants
        ]
        evidence = [
            KernelClaimEvidenceResponse.from_model(item) for item in chain.evidence
        ]
        return cls(
            root_claim=KernelRelationClaimResponse.from_model(chain.root_claim),
            max_depth=chain.max_depth,
            canonical_relations=canonical_relations,
            claims=claims,
            claim_relations=claim_relations,
            participants=participants,
            evidence=evidence,
            counts=KernelGraphViewCountsResponse(
                canonical_relations=len(canonical_relations),
                claims=len(claims),
                claim_relations=len(claim_relations),
                participants=len(participants),
                evidence=len(evidence),
            ),
        )


__all__ = [
    "KernelClaimMechanismChainResponse",
    "KernelGraphDomainViewResponse",
    "KernelGraphViewCountsResponse",
    "KernelSourceDocumentResponse",
]
