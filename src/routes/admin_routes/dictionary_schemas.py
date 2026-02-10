"""Pydantic schemas for kernel dictionary admin endpoints."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from src.domain.entities.kernel.dictionary import (
    EntityResolutionPolicy,
    RelationConstraint,
    TransformRegistry,
    VariableDefinition,
)
from src.type_definitions.common import JSONObject


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
            created_at=model.created_at,
            updated_at=model.updated_at,
        )


class RelationConstraintListResponse(BaseModel):
    """List response payload for relation constraints."""

    model_config = ConfigDict(strict=True)

    constraints: list[RelationConstraintResponse]
    total: int
