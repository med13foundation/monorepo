# ruff: noqa: TC001,TC003
"""Relation, claim, and evidence schemas for kernel graph routes."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from src.domain.entities.kernel.claim_evidence import KernelClaimEvidence
from src.domain.entities.kernel.relation_claims import (
    KernelRelationClaim,
    KernelRelationConflictSummary,
)
from src.domain.entities.kernel.relations import KernelRelation
from src.type_definitions.common import JSONObject
from src.type_definitions.graph_api_schemas.kernel_schema_common import (
    _to_required_utc_datetime,
    _to_utc_datetime,
    _to_uuid,
)


class KernelRelationCreateRequest(BaseModel):
    """Request model for creating a kernel relation (graph edge)."""

    model_config = ConfigDict(strict=False)

    source_id: UUID
    relation_type: str = Field(..., min_length=1, max_length=64)
    target_id: UUID
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    evidence_summary: str | None = None
    evidence_sentence: str | None = Field(default=None, max_length=2000)
    evidence_sentence_source: str | None = Field(default=None, max_length=64)
    evidence_sentence_confidence: str | None = Field(default=None, max_length=32)
    evidence_sentence_rationale: str | None = Field(default=None, max_length=2000)
    evidence_tier: str | None = Field(None, max_length=32)
    provenance_id: UUID | None = None
    source_document_ref: str | None = Field(default=None, max_length=512)


class KernelRelationCurationUpdateRequest(BaseModel):
    """Request model for updating relation curation status."""

    model_config = ConfigDict(strict=True)

    curation_status: str = Field(..., min_length=1, max_length=32)


class KernelRelationClaimTriageRequest(BaseModel):
    """Request model for triaging relation-claim status."""

    model_config = ConfigDict(strict=True)

    claim_status: str = Field(..., min_length=1, max_length=32)


class KernelRelationClaimCreateRequest(BaseModel):
    """Request model for creating a relation claim without materializing it."""

    model_config = ConfigDict(strict=False)

    source_entity_id: UUID
    target_entity_id: UUID
    relation_type: str = Field(..., min_length=1, max_length=64)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    claim_text: str | None = Field(default=None, max_length=4000)
    evidence_summary: str | None = Field(default=None, max_length=2000)
    evidence_sentence: str | None = Field(default=None, max_length=4000)
    evidence_sentence_source: str | None = Field(default=None, max_length=32)
    evidence_sentence_confidence: str | None = Field(default=None, max_length=32)
    evidence_sentence_rationale: str | None = Field(default=None, max_length=4000)
    source_document_ref: str | None = Field(default=None, max_length=512)
    agent_run_id: str | None = Field(default=None, max_length=255)
    metadata: JSONObject = Field(default_factory=dict)


class KernelRelationPaperLinkResponse(BaseModel):
    """One source-paper link for relation evidence review."""

    model_config = ConfigDict(strict=True)

    label: str
    url: str
    source: str


class KernelRelationResponse(BaseModel):
    """Response model for a kernel relation."""

    model_config = ConfigDict(strict=True)

    id: UUID
    research_space_id: UUID
    source_id: UUID
    relation_type: str
    target_id: UUID
    confidence: float
    aggregate_confidence: float
    source_count: int
    highest_evidence_tier: str | None
    curation_status: str
    evidence_summary: str | None = None
    evidence_sentence: str | None = None
    evidence_sentence_source: str | None = None
    evidence_sentence_confidence: str | None = None
    evidence_sentence_rationale: str | None = None
    paper_links: list[KernelRelationPaperLinkResponse] = Field(default_factory=list)
    provenance_id: UUID | None
    reviewed_by: UUID | None
    reviewed_at: datetime | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def _normalize_paper_links(
        cls,
        paper_links: list[KernelRelationPaperLinkResponse] | None,
    ) -> list[KernelRelationPaperLinkResponse]:
        if paper_links is None:
            return []
        return paper_links

    @classmethod
    def from_model(  # noqa: PLR0913
        cls,
        model: KernelRelation,
        *,
        evidence_summary: str | None = None,
        evidence_sentence: str | None = None,
        evidence_sentence_source: str | None = None,
        evidence_sentence_confidence: str | None = None,
        evidence_sentence_rationale: str | None = None,
        paper_links: list[KernelRelationPaperLinkResponse] | None = None,
    ) -> KernelRelationResponse:
        provenance_id_raw = model.provenance_id
        reviewed_by_raw = model.reviewed_by
        return cls(
            id=_to_uuid(model.id),
            research_space_id=_to_uuid(model.research_space_id),
            source_id=_to_uuid(model.source_id),
            relation_type=str(model.relation_type),
            target_id=_to_uuid(model.target_id),
            confidence=float(model.aggregate_confidence),
            aggregate_confidence=float(model.aggregate_confidence),
            source_count=int(model.source_count),
            highest_evidence_tier=model.highest_evidence_tier,
            curation_status=str(model.curation_status),
            evidence_summary=evidence_summary,
            evidence_sentence=evidence_sentence,
            evidence_sentence_source=evidence_sentence_source,
            evidence_sentence_confidence=evidence_sentence_confidence,
            evidence_sentence_rationale=evidence_sentence_rationale,
            paper_links=cls._normalize_paper_links(paper_links),
            provenance_id=(
                _to_uuid(provenance_id_raw) if provenance_id_raw is not None else None
            ),
            reviewed_by=(
                _to_uuid(reviewed_by_raw) if reviewed_by_raw is not None else None
            ),
            reviewed_at=_to_utc_datetime(model.reviewed_at),
            created_at=_to_required_utc_datetime(
                model.created_at,
                field_name="relation.created_at",
            ),
            updated_at=_to_required_utc_datetime(
                model.updated_at,
                field_name="relation.updated_at",
            ),
        )


class KernelRelationListResponse(BaseModel):
    """List response for relations within a research space."""

    model_config = ConfigDict(strict=True)

    relations: list[KernelRelationResponse]
    total: int
    offset: int
    limit: int


class KernelRelationClaimResponse(BaseModel):
    """Response model for one extraction relation claim."""

    model_config = ConfigDict(strict=True)

    id: UUID
    research_space_id: UUID
    source_document_id: UUID | None = None
    source_document_ref: str | None = None
    agent_run_id: str | None = None
    source_type: str
    relation_type: str
    target_type: str
    source_label: str | None
    target_label: str | None
    confidence: float
    validation_state: str
    validation_reason: str | None
    persistability: str
    claim_status: str
    polarity: str
    claim_text: str | None
    claim_section: str | None
    linked_relation_id: UUID | None
    metadata: JSONObject
    triaged_by: UUID | None
    triaged_at: datetime | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, model: KernelRelationClaim) -> KernelRelationClaimResponse:
        source_document_id_raw = getattr(model, "source_document_id", None)
        linked_relation_id_raw = getattr(model, "linked_relation_id", None)
        triaged_by_raw = getattr(model, "triaged_by", None)
        metadata_payload = getattr(model, "metadata_payload", {}) or {}
        return cls(
            id=_to_uuid(model.id),
            research_space_id=_to_uuid(model.research_space_id),
            source_document_id=(
                _to_uuid(source_document_id_raw)
                if source_document_id_raw is not None
                else None
            ),
            source_document_ref=getattr(model, "source_document_ref", None),
            agent_run_id=model.agent_run_id,
            source_type=str(model.source_type),
            relation_type=str(model.relation_type),
            target_type=str(model.target_type),
            source_label=model.source_label,
            target_label=model.target_label,
            confidence=float(model.confidence),
            validation_state=str(model.validation_state),
            validation_reason=model.validation_reason,
            persistability=str(model.persistability),
            claim_status=str(model.claim_status),
            polarity=str(model.polarity),
            claim_text=model.claim_text,
            claim_section=model.claim_section,
            linked_relation_id=(
                _to_uuid(linked_relation_id_raw)
                if linked_relation_id_raw is not None
                else None
            ),
            metadata=dict(metadata_payload),
            triaged_by=(
                _to_uuid(triaged_by_raw) if triaged_by_raw is not None else None
            ),
            triaged_at=_to_utc_datetime(model.triaged_at),
            created_at=_to_required_utc_datetime(
                model.created_at,
                field_name="claim.created_at",
            ),
            updated_at=_to_required_utc_datetime(
                model.updated_at,
                field_name="claim.updated_at",
            ),
        )


class KernelRelationClaimListResponse(BaseModel):
    """List response for relation claims in one research space."""

    model_config = ConfigDict(strict=True)

    claims: list[KernelRelationClaimResponse]
    total: int
    offset: int
    limit: int


class KernelClaimEvidenceResponse(BaseModel):
    """Response model for one claim evidence row."""

    model_config = ConfigDict(strict=True)

    id: UUID
    claim_id: UUID
    source_document_id: UUID | None = None
    source_document_ref: str | None = None
    agent_run_id: str | None = None
    sentence: str | None
    sentence_source: str | None
    sentence_confidence: str | None
    sentence_rationale: str | None
    figure_reference: str | None
    table_reference: str | None
    confidence: float
    metadata: JSONObject
    paper_links: list[KernelRelationPaperLinkResponse] = Field(default_factory=list)
    created_at: datetime

    @classmethod
    def from_model(
        cls,
        model: KernelClaimEvidence,
        *,
        paper_links: list[KernelRelationPaperLinkResponse] | None = None,
    ) -> KernelClaimEvidenceResponse:
        source_document_id_raw = getattr(model, "source_document_id", None)
        metadata_payload = getattr(model, "metadata_payload", {}) or {}
        return cls(
            id=_to_uuid(model.id),
            claim_id=_to_uuid(model.claim_id),
            source_document_id=(
                _to_uuid(source_document_id_raw)
                if source_document_id_raw is not None
                else None
            ),
            source_document_ref=getattr(model, "source_document_ref", None),
            agent_run_id=model.agent_run_id,
            sentence=model.sentence,
            sentence_source=model.sentence_source,
            sentence_confidence=model.sentence_confidence,
            sentence_rationale=model.sentence_rationale,
            figure_reference=model.figure_reference,
            table_reference=model.table_reference,
            confidence=float(model.confidence),
            metadata=dict(metadata_payload),
            paper_links=[] if paper_links is None else paper_links,
            created_at=_to_required_utc_datetime(
                model.created_at,
                field_name="claim_evidence.created_at",
            ),
        )


class KernelClaimEvidenceListResponse(BaseModel):
    """List response for claim evidence rows."""

    model_config = ConfigDict(strict=True)

    claim_id: UUID
    evidence: list[KernelClaimEvidenceResponse]
    total: int


class KernelRelationConflictResponse(BaseModel):
    """Conflict summary for one canonical relation."""

    model_config = ConfigDict(strict=True)

    relation_id: UUID
    support_count: int
    refute_count: int
    support_claim_ids: list[UUID]
    refute_claim_ids: list[UUID]

    @classmethod
    def from_model(
        cls,
        model: KernelRelationConflictSummary,
    ) -> KernelRelationConflictResponse:
        return cls(
            relation_id=_to_uuid(model.relation_id),
            support_count=int(model.support_count),
            refute_count=int(model.refute_count),
            support_claim_ids=[
                _to_uuid(claim_id) for claim_id in model.support_claim_ids
            ],
            refute_claim_ids=[
                _to_uuid(claim_id) for claim_id in model.refute_claim_ids
            ],
        )


class KernelRelationConflictListResponse(BaseModel):
    """List response for mixed-polarity relation conflicts."""

    model_config = ConfigDict(strict=True)

    conflicts: list[KernelRelationConflictResponse]
    total: int
    offset: int
    limit: int
