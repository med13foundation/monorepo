"""Pydantic schemas for kernel (entities/observations/relations/provenance) routes."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from src.domain.entities.kernel.entities import KernelEntity
from src.domain.entities.kernel.observations import KernelObservation
from src.domain.entities.kernel.provenance import KernelProvenanceRecord
from src.domain.entities.kernel.relation_claims import KernelRelationClaim
from src.domain.entities.kernel.relations import KernelRelation
from src.type_definitions.common import JSONObject, JSONValue


def _to_uuid(value: str | UUID) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))


class KernelEntityCreateRequest(BaseModel):
    """Request model for creating (or resolving) a kernel entity."""

    model_config = ConfigDict(strict=True)

    entity_type: str = Field(..., min_length=1, max_length=64)
    display_label: str | None = Field(None, max_length=512)
    metadata: JSONObject = Field(default_factory=dict)
    identifiers: dict[str, str] = Field(
        default_factory=dict,
        description="Namespace -> identifier value (e.g. {'pmid': '12345'})",
    )


class KernelEntityUpdateRequest(BaseModel):
    """Request model for updating a kernel entity."""

    model_config = ConfigDict(strict=True)

    display_label: str | None = Field(None, max_length=512)
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
            metadata=dict(metadata_payload),
            created_at=model.created_at,
            updated_at=model.updated_at,
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
            value_date=model.value_date,
            value_coded=model.value_coded,
            value_boolean=model.value_boolean,
            value_json=model.value_json,
            unit=model.unit,
            observed_at=model.observed_at,
            provenance_id=provenance_id,
            confidence=float(model.confidence),
            created_at=model.created_at,
            updated_at=model.updated_at,
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
    evidence_tier: str | None = Field(None, max_length=32)
    provenance_id: UUID | None = None


class KernelRelationCurationUpdateRequest(BaseModel):
    """Request model for updating relation curation status."""

    model_config = ConfigDict(strict=True)

    curation_status: str = Field(..., min_length=1, max_length=32)


class KernelRelationClaimTriageRequest(BaseModel):
    """Request model for triaging relation-claim status."""

    model_config = ConfigDict(strict=True)

    claim_status: str = Field(..., min_length=1, max_length=32)


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

    provenance_id: UUID | None
    reviewed_by: UUID | None
    reviewed_at: datetime | None

    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, model: KernelRelation) -> KernelRelationResponse:
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
            provenance_id=(
                _to_uuid(provenance_id_raw) if provenance_id_raw is not None else None
            ),
            reviewed_by=(
                _to_uuid(reviewed_by_raw) if reviewed_by_raw is not None else None
            ),
            reviewed_at=model.reviewed_at,
            created_at=model.created_at,
            updated_at=model.updated_at,
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
    source_document_id: UUID | None
    agent_run_id: str | None
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
            linked_relation_id=(
                _to_uuid(linked_relation_id_raw)
                if linked_relation_id_raw is not None
                else None
            ),
            metadata=dict(metadata_payload),
            triaged_by=(
                _to_uuid(triaged_by_raw) if triaged_by_raw is not None else None
            ),
            triaged_at=model.triaged_at,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )


class KernelRelationClaimListResponse(BaseModel):
    """List response for relation claims in one research space."""

    model_config = ConfigDict(strict=True)

    claims: list[KernelRelationClaimResponse]
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
            created_at=model.created_at,
            updated_at=model.updated_at,
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
