"""Pydantic schemas for kernel dictionary admin endpoints."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.domain.entities.kernel.dictionary import (
    DictionaryChangelog,
    DictionaryEntityType,
    DictionaryRelationType,
    DictionarySearchResult,
    EntityResolutionPolicy,
    RelationConstraint,
    TransformRegistry,
    ValueSet,
    ValueSetItem,
    VariableDefinition,
)
from src.type_definitions.common import JSONObject


def _coerce_embedding(value: object) -> list[float] | None:
    """Normalize database embedding payloads to a float list."""
    if isinstance(value, list):
        return [float(item) for item in value]
    if isinstance(value, tuple):
        return [float(item) for item in value]
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            stripped = stripped[1:-1]
        if not stripped:
            return []
        return [float(token) for token in stripped.split(",") if token.strip()]
    return None


class KernelDataType(str, Enum):
    """Allowed kernel dictionary data types."""

    INTEGER = "INTEGER"
    FLOAT = "FLOAT"
    STRING = "STRING"
    DATE = "DATE"
    CODED = "CODED"
    BOOLEAN = "BOOLEAN"
    JSON = "JSON"


class KernelSensitivity(str, Enum):
    """Sensitivity classification for dictionary variables and identifiers."""

    PUBLIC = "PUBLIC"
    INTERNAL = "INTERNAL"
    PHI = "PHI"


class KernelReviewStatus(str, Enum):
    """Review lifecycle states for dictionary entries."""

    ACTIVE = "ACTIVE"
    PENDING_REVIEW = "PENDING_REVIEW"
    REVOKED = "REVOKED"


class KernelDictionaryDimension(str, Enum):
    """Search dimensions supported by dictionary_search."""

    VARIABLES = "variables"
    ENTITY_TYPES = "entity_types"
    RELATION_TYPES = "relation_types"
    CONSTRAINTS = "constraints"


class KernelSearchMatchMethod(str, Enum):
    """Search ranking match methods."""

    EXACT = "exact"
    SYNONYM = "synonym"
    FUZZY = "fuzzy"
    VECTOR = "vector"


class VariableDefinitionCreateRequest(BaseModel):
    """Request payload for creating a dictionary variable."""

    # Incoming JSON should be able to provide enum values as strings.
    model_config = ConfigDict(strict=False)

    id: str = Field(..., min_length=1, max_length=64, description="Variable ID")
    canonical_name: str = Field(..., min_length=1, max_length=128)
    display_name: str = Field(..., min_length=1, max_length=255)
    data_type: KernelDataType
    domain_context: str = Field(default="general", min_length=1, max_length=64)
    sensitivity: KernelSensitivity = KernelSensitivity.INTERNAL
    preferred_unit: str | None = Field(None, max_length=64)
    constraints: JSONObject = Field(default_factory=dict)
    description: str | None = None
    source_ref: str | None = Field(
        default=None,
        max_length=1024,
        description="Optional source reference for provenance tracking",
    )


class VariableDefinitionResponse(BaseModel):
    """Response payload for a dictionary variable."""

    model_config = ConfigDict(strict=True)

    id: str
    canonical_name: str
    display_name: str
    data_type: KernelDataType
    preferred_unit: str | None
    constraints: JSONObject
    domain_context: str
    sensitivity: KernelSensitivity
    description: str | None
    description_embedding: list[float] | None
    embedded_at: datetime | None
    embedding_model: str | None
    created_by: str
    source_ref: str | None
    review_status: KernelReviewStatus
    reviewed_by: str | None
    reviewed_at: datetime | None
    revocation_reason: str | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, model: VariableDefinition) -> VariableDefinitionResponse:
        return cls(
            id=str(model.id),
            canonical_name=str(model.canonical_name),
            display_name=str(model.display_name),
            data_type=KernelDataType(str(model.data_type)),
            preferred_unit=str(model.preferred_unit) if model.preferred_unit else None,
            constraints=dict(model.constraints) if model.constraints else {},
            domain_context=str(model.domain_context),
            sensitivity=KernelSensitivity(str(model.sensitivity)),
            description=str(model.description) if model.description else None,
            description_embedding=_coerce_embedding(model.description_embedding),
            embedded_at=model.embedded_at,
            embedding_model=(
                str(model.embedding_model) if model.embedding_model else None
            ),
            created_by=str(model.created_by),
            source_ref=str(model.source_ref) if model.source_ref else None,
            review_status=KernelReviewStatus(str(model.review_status)),
            reviewed_by=str(model.reviewed_by) if model.reviewed_by else None,
            reviewed_at=model.reviewed_at,
            revocation_reason=(
                str(model.revocation_reason) if model.revocation_reason else None
            ),
            created_at=model.created_at,
            updated_at=model.updated_at,
        )


class VariableDefinitionListResponse(BaseModel):
    """List response payload for dictionary variables."""

    model_config = ConfigDict(strict=True)

    variables: list[VariableDefinitionResponse]
    total: int


class TransformRegistryResponse(BaseModel):
    """Response payload for a transform registry record."""

    model_config = ConfigDict(strict=True)

    id: str
    input_unit: str
    output_unit: str
    implementation_ref: str
    status: str
    created_by: str
    source_ref: str | None
    review_status: KernelReviewStatus
    reviewed_by: str | None
    reviewed_at: datetime | None
    revocation_reason: str | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, model: TransformRegistry) -> TransformRegistryResponse:
        return cls(
            id=str(model.id),
            input_unit=str(model.input_unit),
            output_unit=str(model.output_unit),
            implementation_ref=str(model.implementation_ref),
            status=str(model.status),
            created_by=str(model.created_by),
            source_ref=str(model.source_ref) if model.source_ref else None,
            review_status=KernelReviewStatus(str(model.review_status)),
            reviewed_by=str(model.reviewed_by) if model.reviewed_by else None,
            reviewed_at=model.reviewed_at,
            revocation_reason=(
                str(model.revocation_reason) if model.revocation_reason else None
            ),
            created_at=model.created_at,
            updated_at=model.updated_at,
        )


class TransformRegistryListResponse(BaseModel):
    """List response payload for transform registry records."""

    model_config = ConfigDict(strict=True)

    transforms: list[TransformRegistryResponse]
    total: int


class EntityResolutionPolicyResponse(BaseModel):
    """Response payload for an entity resolution policy."""

    model_config = ConfigDict(strict=True)

    entity_type: str
    policy_strategy: str
    required_anchors: list[str]
    auto_merge_threshold: float
    created_by: str
    source_ref: str | None
    review_status: KernelReviewStatus
    reviewed_by: str | None
    reviewed_at: datetime | None
    revocation_reason: str | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(
        cls,
        model: EntityResolutionPolicy,
    ) -> EntityResolutionPolicyResponse:
        anchors = (
            model.required_anchors if isinstance(model.required_anchors, list) else []
        )
        return cls(
            entity_type=str(model.entity_type),
            policy_strategy=str(model.policy_strategy),
            required_anchors=[str(a) for a in anchors],
            auto_merge_threshold=float(model.auto_merge_threshold),
            created_by=str(model.created_by),
            source_ref=str(model.source_ref) if model.source_ref else None,
            review_status=KernelReviewStatus(str(model.review_status)),
            reviewed_by=str(model.reviewed_by) if model.reviewed_by else None,
            reviewed_at=model.reviewed_at,
            revocation_reason=(
                str(model.revocation_reason) if model.revocation_reason else None
            ),
            created_at=model.created_at,
            updated_at=model.updated_at,
        )


class EntityResolutionPolicyListResponse(BaseModel):
    """List response payload for entity resolution policies."""

    model_config = ConfigDict(strict=True)

    policies: list[EntityResolutionPolicyResponse]
    total: int


class RelationConstraintResponse(BaseModel):
    """Response payload for a relation constraint (allowed triple)."""

    model_config = ConfigDict(strict=True)

    id: int
    source_type: str
    relation_type: str
    target_type: str
    is_allowed: bool
    requires_evidence: bool
    created_by: str
    source_ref: str | None
    review_status: KernelReviewStatus
    reviewed_by: str | None
    reviewed_at: datetime | None
    revocation_reason: str | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, model: RelationConstraint) -> RelationConstraintResponse:
        return cls(
            id=int(model.id),
            source_type=str(model.source_type),
            relation_type=str(model.relation_type),
            target_type=str(model.target_type),
            is_allowed=bool(model.is_allowed),
            requires_evidence=bool(model.requires_evidence),
            created_by=str(model.created_by),
            source_ref=str(model.source_ref) if model.source_ref else None,
            review_status=KernelReviewStatus(str(model.review_status)),
            reviewed_by=str(model.reviewed_by) if model.reviewed_by else None,
            reviewed_at=model.reviewed_at,
            revocation_reason=(
                str(model.revocation_reason) if model.revocation_reason else None
            ),
            created_at=model.created_at,
            updated_at=model.updated_at,
        )


class RelationConstraintListResponse(BaseModel):
    """List response payload for relation constraints."""

    model_config = ConfigDict(strict=True)

    constraints: list[RelationConstraintResponse]
    total: int


class DictionaryEntityTypeCreateRequest(BaseModel):
    """Request payload for creating a dictionary entity type."""

    model_config = ConfigDict(strict=False)

    id: str = Field(..., min_length=1, max_length=64)
    display_name: str = Field(..., min_length=1, max_length=128)
    description: str = Field(..., min_length=1)
    domain_context: str = Field(..., min_length=1, max_length=64)
    external_ontology_ref: str | None = Field(default=None, max_length=255)
    expected_properties: JSONObject = Field(default_factory=dict)
    source_ref: str | None = Field(default=None, max_length=1024)


class DictionaryEntityTypeResponse(BaseModel):
    """Response payload for a dictionary entity type."""

    model_config = ConfigDict(strict=True)

    id: str
    display_name: str
    description: str
    domain_context: str
    external_ontology_ref: str | None
    expected_properties: JSONObject
    description_embedding: list[float] | None
    embedded_at: datetime | None
    embedding_model: str | None
    created_by: str
    source_ref: str | None
    review_status: KernelReviewStatus
    reviewed_by: str | None
    reviewed_at: datetime | None
    revocation_reason: str | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, model: DictionaryEntityType) -> DictionaryEntityTypeResponse:
        return cls(
            id=str(model.id),
            display_name=str(model.display_name),
            description=str(model.description),
            domain_context=str(model.domain_context),
            external_ontology_ref=(
                str(model.external_ontology_ref)
                if model.external_ontology_ref
                else None
            ),
            expected_properties=(
                dict(model.expected_properties) if model.expected_properties else {}
            ),
            description_embedding=_coerce_embedding(model.description_embedding),
            embedded_at=model.embedded_at,
            embedding_model=(
                str(model.embedding_model) if model.embedding_model else None
            ),
            created_by=str(model.created_by),
            source_ref=str(model.source_ref) if model.source_ref else None,
            review_status=KernelReviewStatus(str(model.review_status)),
            reviewed_by=str(model.reviewed_by) if model.reviewed_by else None,
            reviewed_at=model.reviewed_at,
            revocation_reason=(
                str(model.revocation_reason) if model.revocation_reason else None
            ),
            created_at=model.created_at,
            updated_at=model.updated_at,
        )


class DictionaryEntityTypeListResponse(BaseModel):
    """List response payload for dictionary entity types."""

    model_config = ConfigDict(strict=True)

    entity_types: list[DictionaryEntityTypeResponse]
    total: int


class DictionaryRelationTypeCreateRequest(BaseModel):
    """Request payload for creating a dictionary relation type."""

    model_config = ConfigDict(strict=False)

    id: str = Field(..., min_length=1, max_length=64)
    display_name: str = Field(..., min_length=1, max_length=128)
    description: str = Field(..., min_length=1)
    domain_context: str = Field(..., min_length=1, max_length=64)
    is_directional: bool = True
    inverse_label: str | None = Field(default=None, max_length=128)
    source_ref: str | None = Field(default=None, max_length=1024)


class DictionaryRelationTypeResponse(BaseModel):
    """Response payload for a dictionary relation type."""

    model_config = ConfigDict(strict=True)

    id: str
    display_name: str
    description: str
    domain_context: str
    is_directional: bool
    inverse_label: str | None
    description_embedding: list[float] | None
    embedded_at: datetime | None
    embedding_model: str | None
    created_by: str
    source_ref: str | None
    review_status: KernelReviewStatus
    reviewed_by: str | None
    reviewed_at: datetime | None
    revocation_reason: str | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(
        cls,
        model: DictionaryRelationType,
    ) -> DictionaryRelationTypeResponse:
        return cls(
            id=str(model.id),
            display_name=str(model.display_name),
            description=str(model.description),
            domain_context=str(model.domain_context),
            is_directional=bool(model.is_directional),
            inverse_label=str(model.inverse_label) if model.inverse_label else None,
            description_embedding=_coerce_embedding(model.description_embedding),
            embedded_at=model.embedded_at,
            embedding_model=(
                str(model.embedding_model) if model.embedding_model else None
            ),
            created_by=str(model.created_by),
            source_ref=str(model.source_ref) if model.source_ref else None,
            review_status=KernelReviewStatus(str(model.review_status)),
            reviewed_by=str(model.reviewed_by) if model.reviewed_by else None,
            reviewed_at=model.reviewed_at,
            revocation_reason=(
                str(model.revocation_reason) if model.revocation_reason else None
            ),
            created_at=model.created_at,
            updated_at=model.updated_at,
        )


class DictionaryRelationTypeListResponse(BaseModel):
    """List response payload for dictionary relation types."""

    model_config = ConfigDict(strict=True)

    relation_types: list[DictionaryRelationTypeResponse]
    total: int


class ValueSetCreateRequest(BaseModel):
    """Request payload for creating a dictionary value set."""

    model_config = ConfigDict(strict=False)

    id: str = Field(..., min_length=1, max_length=64)
    variable_id: str = Field(..., min_length=1, max_length=64)
    name: str = Field(..., min_length=1, max_length=128)
    description: str | None = None
    external_ref: str | None = Field(default=None, max_length=255)
    is_extensible: bool = False
    source_ref: str | None = Field(default=None, max_length=1024)


class ValueSetResponse(BaseModel):
    """Response payload for a dictionary value set."""

    model_config = ConfigDict(strict=True)

    id: str
    variable_id: str
    variable_data_type: str
    name: str
    description: str | None
    external_ref: str | None
    is_extensible: bool
    created_by: str
    source_ref: str | None
    review_status: KernelReviewStatus
    reviewed_by: str | None
    reviewed_at: datetime | None
    revocation_reason: str | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, model: ValueSet) -> ValueSetResponse:
        return cls(
            id=str(model.id),
            variable_id=str(model.variable_id),
            variable_data_type=str(model.variable_data_type),
            name=str(model.name),
            description=str(model.description) if model.description else None,
            external_ref=str(model.external_ref) if model.external_ref else None,
            is_extensible=bool(model.is_extensible),
            created_by=str(model.created_by),
            source_ref=str(model.source_ref) if model.source_ref else None,
            review_status=KernelReviewStatus(str(model.review_status)),
            reviewed_by=str(model.reviewed_by) if model.reviewed_by else None,
            reviewed_at=model.reviewed_at,
            revocation_reason=(
                str(model.revocation_reason) if model.revocation_reason else None
            ),
            created_at=model.created_at,
            updated_at=model.updated_at,
        )


class ValueSetListResponse(BaseModel):
    """List response payload for dictionary value sets."""

    model_config = ConfigDict(strict=True)

    value_sets: list[ValueSetResponse]
    total: int


class ValueSetItemCreateRequest(BaseModel):
    """Request payload for creating a value set item."""

    model_config = ConfigDict(strict=False)

    code: str = Field(..., min_length=1, max_length=128)
    display_label: str = Field(..., min_length=1, max_length=255)
    synonyms: list[str] = Field(default_factory=list)
    external_ref: str | None = Field(default=None, max_length=255)
    sort_order: int = 0
    is_active: bool = True
    source_ref: str | None = Field(default=None, max_length=1024)


class ValueSetItemResponse(BaseModel):
    """Response payload for a dictionary value set item."""

    model_config = ConfigDict(strict=True)

    id: int
    value_set_id: str
    code: str
    display_label: str
    synonyms: list[str]
    external_ref: str | None
    sort_order: int
    is_active: bool
    created_by: str
    source_ref: str | None
    review_status: KernelReviewStatus
    reviewed_by: str | None
    reviewed_at: datetime | None
    revocation_reason: str | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, model: ValueSetItem) -> ValueSetItemResponse:
        return cls(
            id=int(model.id),
            value_set_id=str(model.value_set_id),
            code=str(model.code),
            display_label=str(model.display_label),
            synonyms=list(model.synonyms) if isinstance(model.synonyms, list) else [],
            external_ref=str(model.external_ref) if model.external_ref else None,
            sort_order=int(model.sort_order),
            is_active=bool(model.is_active),
            created_by=str(model.created_by),
            source_ref=str(model.source_ref) if model.source_ref else None,
            review_status=KernelReviewStatus(str(model.review_status)),
            reviewed_by=str(model.reviewed_by) if model.reviewed_by else None,
            reviewed_at=model.reviewed_at,
            revocation_reason=(
                str(model.revocation_reason) if model.revocation_reason else None
            ),
            created_at=model.created_at,
            updated_at=model.updated_at,
        )


class ValueSetItemListResponse(BaseModel):
    """List response payload for dictionary value set items."""

    model_config = ConfigDict(strict=True)

    items: list[ValueSetItemResponse]
    total: int


class ValueSetItemActiveRequest(BaseModel):
    """Request payload for activating/deactivating a value set item."""

    model_config = ConfigDict(strict=False)

    is_active: bool
    revocation_reason: str | None = Field(
        default=None,
        description="Required when is_active is false",
    )

    @model_validator(mode="after")
    def validate_reason(self) -> ValueSetItemActiveRequest:
        """Enforce reason semantics for deactivation updates."""
        if not self.is_active:
            if self.revocation_reason is None or not self.revocation_reason.strip():
                msg = "revocation_reason is required when deactivating a value set item"
                raise ValueError(msg)
        elif self.revocation_reason is not None:
            msg = "revocation_reason is only valid when deactivating a value set item"
            raise ValueError(msg)
        return self


class DictionaryChangelogResponse(BaseModel):
    """Response payload for a dictionary changelog entry."""

    model_config = ConfigDict(strict=True)

    id: int
    table_name: str
    record_id: str
    action: str
    before_snapshot: JSONObject | None
    after_snapshot: JSONObject | None
    changed_by: str | None
    source_ref: str | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, model: DictionaryChangelog) -> DictionaryChangelogResponse:
        return cls(
            id=int(model.id),
            table_name=str(model.table_name),
            record_id=str(model.record_id),
            action=str(model.action),
            before_snapshot=(
                dict(model.before_snapshot)
                if model.before_snapshot is not None
                else None
            ),
            after_snapshot=(
                dict(model.after_snapshot) if model.after_snapshot is not None else None
            ),
            changed_by=str(model.changed_by) if model.changed_by else None,
            source_ref=str(model.source_ref) if model.source_ref else None,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )


class DictionaryChangelogListResponse(BaseModel):
    """List response payload for dictionary changelog entries."""

    model_config = ConfigDict(strict=True)

    changelog_entries: list[DictionaryChangelogResponse]
    total: int


class DictionarySearchResultResponse(BaseModel):
    """Response payload for one dictionary search hit."""

    model_config = ConfigDict(strict=True)

    dimension: KernelDictionaryDimension
    entry_id: str
    display_name: str
    description: str | None
    domain_context: str | None
    match_method: KernelSearchMatchMethod
    similarity_score: float
    metadata: JSONObject

    @classmethod
    def from_model(
        cls,
        model: DictionarySearchResult,
    ) -> DictionarySearchResultResponse:
        return cls(
            dimension=KernelDictionaryDimension(model.dimension),
            entry_id=str(model.entry_id),
            display_name=str(model.display_name),
            description=str(model.description) if model.description else None,
            domain_context=str(model.domain_context) if model.domain_context else None,
            match_method=KernelSearchMatchMethod(model.match_method),
            similarity_score=float(model.similarity_score),
            metadata=dict(model.metadata) if model.metadata else {},
        )


class DictionarySearchListResponse(BaseModel):
    """List response payload for dictionary search endpoints."""

    model_config = ConfigDict(strict=True)

    results: list[DictionarySearchResultResponse]
    total: int


class DictionaryReembedRequest(BaseModel):
    """Request payload for dictionary embedding refresh jobs."""

    model_config = ConfigDict(strict=False)

    model_name: str | None = Field(
        default=None,
        max_length=64,
        description="Embedding model to use (defaults to service setting)",
    )
    limit_per_dimension: int | None = Field(
        default=None,
        ge=1,
        le=5000,
        description="Optional cap per dimension for partial re-embed runs",
    )
    source_ref: str | None = Field(
        default=None,
        max_length=1024,
        description="Optional provenance pointer for the refresh request",
    )


class DictionaryReembedResponse(BaseModel):
    """Response payload for dictionary embedding refresh jobs."""

    model_config = ConfigDict(strict=True)

    updated_records: int
    model_name: str | None


class VariableDefinitionReviewStatusRequest(BaseModel):
    """Request payload for dictionary variable review-status updates."""

    model_config = ConfigDict(strict=False)

    review_status: KernelReviewStatus
    revocation_reason: str | None = Field(
        default=None,
        description="Required when review_status is REVOKED",
    )

    @model_validator(mode="after")
    def validate_reason(self) -> VariableDefinitionReviewStatusRequest:
        """Enforce reason semantics for revocation updates."""
        if self.review_status == KernelReviewStatus.REVOKED:
            if self.revocation_reason is None or not self.revocation_reason.strip():
                msg = "revocation_reason is required when review_status is REVOKED"
                raise ValueError(msg)
        elif self.revocation_reason is not None:
            msg = "revocation_reason is only valid for REVOKED status"
            raise ValueError(msg)
        return self


class VariableDefinitionRevokeRequest(BaseModel):
    """Request payload for explicit variable revocation operations."""

    reason: str = Field(..., min_length=1)
