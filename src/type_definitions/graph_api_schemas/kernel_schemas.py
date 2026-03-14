# ruff: noqa: TC001,TC003
"""Pydantic schemas for kernel (entities/observations/relations/provenance) routes."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from src.domain.entities.kernel.claim_evidence import KernelClaimEvidence
from src.domain.entities.kernel.entities import KernelEntity
from src.domain.entities.kernel.observations import KernelObservation
from src.domain.entities.kernel.provenance import KernelProvenanceRecord
from src.domain.entities.kernel.relation_claims import (
    KernelRelationClaim,
    KernelRelationConflictSummary,
)
from src.domain.entities.kernel.relations import KernelRelation
from src.type_definitions.common import JSONObject, JSONValue


def _to_uuid(value: str | UUID) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))


def _to_utc_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


class KernelEntityCreateRequest(BaseModel):
    """Request model for creating (or resolving) a kernel entity."""

    model_config = ConfigDict(strict=True)

    entity_type: str = Field(..., min_length=1, max_length=64)
    display_label: str | None = Field(None, max_length=512)
    aliases: list[str] = Field(default_factory=list)
    metadata: JSONObject = Field(default_factory=dict)
    identifiers: dict[str, str] = Field(
        default_factory=dict,
        description="Namespace -> identifier value (e.g. {'pmid': '12345'})",
    )


class KernelEntityUpdateRequest(BaseModel):
    """Request model for updating a kernel entity."""

    model_config = ConfigDict(strict=True)

    display_label: str | None = Field(None, max_length=512)
    aliases: list[str] | None = None
    metadata: JSONObject | None = None
    identifiers: dict[str, str] | None = Field(
        default=None,
        description="Namespace -> identifier value pairs to add (merge-only).",
    )


class KernelEntityResponse(BaseModel):
    """Response model for a kernel entity."""

    model_config = ConfigDict(strict=True)

    id: UUID
    research_space_id: UUID
    entity_type: str
    display_label: str | None
    aliases: list[str] = Field(default_factory=list)
    metadata: JSONObject
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, model: KernelEntity) -> KernelEntityResponse:
        entity_id = _to_uuid(model.id)
        space_id = _to_uuid(model.research_space_id)
        metadata_payload = model.metadata or {}
        return cls(
            id=entity_id,
            research_space_id=space_id,
            entity_type=str(model.entity_type),
            display_label=str(model.display_label) if model.display_label else None,
            aliases=[
                str(alias)
                for alias in model.aliases
                if isinstance(alias, str) and alias.strip()
            ],
            metadata=dict(metadata_payload),
            created_at=_to_utc_datetime(model.created_at),
            updated_at=_to_utc_datetime(model.updated_at),
        )


class KernelEntityUpsertResponse(BaseModel):
    """Response for create-or-resolve operations."""

    model_config = ConfigDict(strict=True)

    entity: KernelEntityResponse
    created: bool


class KernelEntityListResponse(BaseModel):
    """List response for entities within a research space."""

    model_config = ConfigDict(strict=True)

    entities: list[KernelEntityResponse]
    total: int
    offset: int
    limit: int


class KernelEntitySimilarityScoreBreakdownResponse(BaseModel):
    """Score components for one similar-entity result row."""

    model_config = ConfigDict(strict=True)

    vector_score: float = Field(ge=0.0, le=1.0)
    graph_overlap_score: float = Field(ge=0.0, le=1.0)


class KernelEntitySimilarityResponse(BaseModel):
    """One similar-entity result row."""

    model_config = ConfigDict(strict=True)

    entity_id: UUID
    entity_type: str = Field(min_length=1, max_length=64)
    display_label: str | None = Field(default=None, max_length=512)
    similarity_score: float = Field(ge=0.0, le=1.0)
    score_breakdown: KernelEntitySimilarityScoreBreakdownResponse


class KernelEntitySimilarityListResponse(BaseModel):
    """List response for similar entities in one research space."""

    model_config = ConfigDict(strict=True)

    source_entity_id: UUID
    results: list[KernelEntitySimilarityResponse]
    total: int
    limit: int
    min_similarity: float = Field(ge=0.0, le=1.0)


class KernelEntityEmbeddingRefreshRequest(BaseModel):
    """Request payload for explicit kernel entity embedding refresh operations."""

    # UUID input parsing can arrive as strings in request JSON.
    model_config = ConfigDict(strict=False)

    entity_ids: list[UUID] | None = Field(default=None, min_length=1, max_length=500)
    limit: int = Field(default=500, ge=1, le=5000)
    model_name: str | None = Field(default=None, min_length=1, max_length=128)
    embedding_version: int | None = Field(default=None, ge=1, le=1000)


class KernelEntityEmbeddingRefreshResponse(BaseModel):
    """Response summary for explicit embedding refresh operations."""

    model_config = ConfigDict(strict=True)

    requested: int
    processed: int
    refreshed: int
    unchanged: int
    missing_entities: list[str]


class KernelRelationSuggestionRequest(BaseModel):
    """Request payload for dictionary-constrained relation suggestion runs."""

    # UUID input parsing can arrive as strings in request JSON.
    model_config = ConfigDict(strict=False)

    source_entity_ids: list[UUID] = Field(min_length=1, max_length=50)
    limit_per_source: int = Field(default=10, ge=1, le=50)
    min_score: float = Field(default=0.70, ge=0.0, le=1.0)
    allowed_relation_types: list[str] | None = Field(
        default=None,
        min_length=1,
        max_length=200,
    )
    target_entity_types: list[str] | None = Field(
        default=None,
        min_length=1,
        max_length=200,
    )
    exclude_existing_relations: bool = True


class KernelRelationSuggestionScoreBreakdownResponse(BaseModel):
    """Score components for one relation suggestion row."""

    model_config = ConfigDict(strict=True)

    vector_score: float = Field(ge=0.0, le=1.0)
    graph_overlap_score: float = Field(ge=0.0, le=1.0)
    relation_prior_score: float = Field(ge=0.0, le=1.0)


class KernelRelationSuggestionConstraintCheckResponse(BaseModel):
    """Constraint trace proving dictionary validation for a suggestion row."""

    model_config = ConfigDict(strict=True)

    passed: bool
    source_entity_type: str = Field(min_length=1, max_length=64)
    relation_type: str = Field(min_length=1, max_length=64)
    target_entity_type: str = Field(min_length=1, max_length=64)


class KernelRelationSuggestionResponse(BaseModel):
    """One relation suggestion row."""

    model_config = ConfigDict(strict=True)

    source_entity_id: UUID
    target_entity_id: UUID
    relation_type: str = Field(min_length=1, max_length=64)
    final_score: float = Field(ge=0.0, le=1.0)
    score_breakdown: KernelRelationSuggestionScoreBreakdownResponse
    constraint_check: KernelRelationSuggestionConstraintCheckResponse


class KernelRelationSuggestionListResponse(BaseModel):
    """List response for constrained relation suggestions."""

    model_config = ConfigDict(strict=True)

    suggestions: list[KernelRelationSuggestionResponse]
    total: int
    limit_per_source: int
    min_score: float = Field(ge=0.0, le=1.0)


class KernelObservationCreateRequest(BaseModel):
    """Request model for recording a kernel observation."""

    # Incoming JSON provides UUIDs and datetimes as strings.
    model_config = ConfigDict(strict=False)

    subject_id: UUID
    variable_id: str = Field(..., min_length=1, max_length=64)
    value: JSONValue
    unit: str | None = Field(None, max_length=64)
    observed_at: datetime | None = None
    provenance_id: UUID | None = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class KernelObservationResponse(BaseModel):
    """Response model for a kernel observation."""

    model_config = ConfigDict(strict=True)

    id: UUID
    research_space_id: UUID
    subject_id: UUID
    variable_id: str

    value_numeric: float | None
    value_text: str | None
    value_date: datetime | None
    value_coded: str | None
    value_boolean: bool | None
    value_json: JSONValue | None

    unit: str | None
    observed_at: datetime | None
    provenance_id: UUID | None
    confidence: float

    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, model: KernelObservation) -> KernelObservationResponse:
        value_numeric_raw = model.value_numeric
        value_numeric = (
            float(value_numeric_raw) if value_numeric_raw is not None else None
        )

        provenance_id_raw = model.provenance_id
        provenance_id = (
            _to_uuid(provenance_id_raw) if provenance_id_raw is not None else None
        )

        return cls(
            id=_to_uuid(model.id),
            research_space_id=_to_uuid(model.research_space_id),
            subject_id=_to_uuid(model.subject_id),
            variable_id=str(model.variable_id),
            value_numeric=value_numeric,
            value_text=model.value_text,
            value_date=_to_utc_datetime(model.value_date),
            value_coded=model.value_coded,
            value_boolean=model.value_boolean,
            value_json=model.value_json,
            unit=model.unit,
            observed_at=_to_utc_datetime(model.observed_at),
            provenance_id=provenance_id,
            confidence=float(model.confidence),
            created_at=_to_utc_datetime(model.created_at),
            updated_at=_to_utc_datetime(model.updated_at),
        )


class KernelObservationListResponse(BaseModel):
    """List response for observations within a research space."""

    model_config = ConfigDict(strict=True)

    observations: list[KernelObservationResponse]
    total: int
    offset: int
    limit: int


class KernelRelationCreateRequest(BaseModel):
    """Request model for creating a kernel relation (graph edge)."""

    # Incoming JSON provides UUIDs as strings.
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

    # Incoming JSON provides UUIDs as strings.
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
            created_at=_to_utc_datetime(model.created_at),
            updated_at=_to_utc_datetime(model.updated_at),
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
            created_at=_to_utc_datetime(model.created_at),
            updated_at=_to_utc_datetime(model.updated_at),
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
            created_at=_to_utc_datetime(model.created_at),
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


class KernelProvenanceResponse(BaseModel):
    """Response model for a provenance record."""

    model_config = ConfigDict(strict=True)

    id: UUID
    research_space_id: UUID
    source_type: str
    source_ref: str | None
    extraction_run_id: str | None
    mapping_method: str | None
    mapping_confidence: float | None
    agent_model: str | None
    raw_input: JSONObject | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, model: KernelProvenanceRecord) -> KernelProvenanceResponse:
        return cls(
            id=_to_uuid(model.id),
            research_space_id=_to_uuid(model.research_space_id),
            source_type=str(model.source_type),
            source_ref=model.source_ref,
            extraction_run_id=model.extraction_run_id,
            mapping_method=model.mapping_method,
            mapping_confidence=model.mapping_confidence,
            agent_model=model.agent_model,
            raw_input=dict(model.raw_input) if model.raw_input else None,
            created_at=_to_utc_datetime(model.created_at),
            updated_at=_to_utc_datetime(model.updated_at),
        )


class KernelProvenanceListResponse(BaseModel):
    """List response for provenance records."""

    model_config = ConfigDict(strict=True)

    provenance: list[KernelProvenanceResponse]
    total: int
    offset: int
    limit: int


class KernelGraphExportResponse(BaseModel):
    """Graph export response for a research space (nodes + edges)."""

    model_config = ConfigDict(strict=True)

    nodes: list[KernelEntityResponse]
    edges: list[KernelRelationResponse]


class KernelGraphSubgraphRequest(BaseModel):
    """Request payload for bounded subgraph retrieval."""

    # Incoming JSON provides UUIDs as strings.
    model_config = ConfigDict(strict=False)

    mode: Literal["starter", "seeded"]
    seed_entity_ids: list[UUID] = Field(default_factory=list)
    depth: int = Field(default=2, ge=1, le=4)
    top_k: int = Field(default=25, ge=1, le=100)
    relation_types: list[str] | None = None
    curation_statuses: list[str] | None = None
    max_nodes: int = Field(default=180, ge=20, le=500)
    max_edges: int = Field(default=260, ge=20, le=1000)


class KernelGraphSubgraphMeta(BaseModel):
    """Metadata describing bounded-subgraph execution and truncation."""

    model_config = ConfigDict(strict=True)

    mode: Literal["starter", "seeded"]
    seed_entity_ids: list[UUID]
    requested_depth: int
    requested_top_k: int
    pre_cap_node_count: int
    pre_cap_edge_count: int
    truncated_nodes: bool
    truncated_edges: bool


class KernelGraphSubgraphResponse(BaseModel):
    """Bounded subgraph response for interactive graph rendering."""

    model_config = ConfigDict(strict=True)

    nodes: list[KernelEntityResponse]
    edges: list[KernelRelationResponse]
    meta: KernelGraphSubgraphMeta


class KernelGraphDocumentRequest(BaseModel):
    """Request payload for unified graph documents with claim/evidence overlays."""

    # Incoming JSON provides UUIDs as strings.
    model_config = ConfigDict(strict=False)

    mode: Literal["starter", "seeded"]
    seed_entity_ids: list[UUID] = Field(default_factory=list)
    depth: int = Field(default=2, ge=1, le=4)
    top_k: int = Field(default=25, ge=1, le=100)
    relation_types: list[str] | None = None
    curation_statuses: list[str] | None = None
    max_nodes: int = Field(default=180, ge=20, le=500)
    max_edges: int = Field(default=260, ge=20, le=1000)
    include_claims: bool = True
    include_evidence: bool = True
    max_claims: int = Field(default=250, ge=1, le=1000)
    evidence_limit_per_claim: int = Field(default=3, ge=1, le=10)


class KernelGraphDocumentNode(BaseModel):
    """One typed graph node in the unified graph document."""

    model_config = ConfigDict(strict=True)

    id: str = Field(min_length=1, max_length=255)
    resource_id: str = Field(min_length=1, max_length=255)
    kind: Literal["ENTITY", "CLAIM", "EVIDENCE"]
    type_label: str = Field(min_length=1, max_length=64)
    label: str = Field(min_length=1, max_length=512)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    curation_status: str | None = Field(default=None, max_length=32)
    claim_status: str | None = Field(default=None, max_length=32)
    polarity: str | None = Field(default=None, max_length=32)
    canonical_relation_id: UUID | None = None
    metadata: JSONObject = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class KernelGraphDocumentEdge(BaseModel):
    """One typed graph edge in the unified graph document."""

    model_config = ConfigDict(strict=True)

    id: str = Field(min_length=1, max_length=255)
    resource_id: str | None = Field(default=None, max_length=255)
    kind: Literal["CANONICAL_RELATION", "CLAIM_PARTICIPANT", "CLAIM_EVIDENCE"]
    source_id: str = Field(min_length=1, max_length=255)
    target_id: str = Field(min_length=1, max_length=255)
    type_label: str = Field(min_length=1, max_length=64)
    label: str = Field(min_length=1, max_length=512)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    curation_status: str | None = Field(default=None, max_length=32)
    claim_id: UUID | None = None
    canonical_relation_id: UUID | None = None
    evidence_id: UUID | None = None
    metadata: JSONObject = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class KernelGraphDocumentCounts(BaseModel):
    """Per-kind counts returned with a unified graph document."""

    model_config = ConfigDict(strict=True)

    entity_nodes: int = Field(ge=0)
    claim_nodes: int = Field(ge=0)
    evidence_nodes: int = Field(ge=0)
    canonical_edges: int = Field(ge=0)
    claim_participant_edges: int = Field(ge=0)
    claim_evidence_edges: int = Field(ge=0)


class KernelGraphDocumentMeta(BaseModel):
    """Metadata describing graph-document scope and included overlays."""

    model_config = ConfigDict(strict=True)

    mode: Literal["starter", "seeded"]
    seed_entity_ids: list[UUID]
    requested_depth: int
    requested_top_k: int
    pre_cap_entity_node_count: int
    pre_cap_canonical_edge_count: int
    truncated_entity_nodes: bool
    truncated_canonical_edges: bool
    included_claims: bool
    included_evidence: bool
    max_claims: int
    evidence_limit_per_claim: int
    counts: KernelGraphDocumentCounts


class KernelGraphDocumentResponse(BaseModel):
    """Unified graph document containing canonical, claim, and evidence elements."""

    model_config = ConfigDict(strict=True)

    nodes: list[KernelGraphDocumentNode]
    edges: list[KernelGraphDocumentEdge]
    meta: KernelGraphDocumentMeta
