# ruff: noqa: TC001,TC003
"""Entity and suggestion schemas for kernel graph routes."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from src.domain.entities.kernel.entities import KernelEntity
from src.type_definitions.common import JSONObject
from src.type_definitions.graph_api_schemas.kernel_schema_common import (
    _to_required_utc_datetime,
    _to_uuid,
)


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
            created_at=_to_required_utc_datetime(
                model.created_at,
                field_name="entity.created_at",
            ),
            updated_at=_to_required_utc_datetime(
                model.updated_at,
                field_name="entity.updated_at",
            ),
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
