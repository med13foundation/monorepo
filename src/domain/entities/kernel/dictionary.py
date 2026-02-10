"""
Kernel dictionary domain entities (Layer 1 rules).

These are domain-level models used by application services and repositories.
They mirror the kernel dictionary tables but do not depend on SQLAlchemy.
"""

from __future__ import annotations

from datetime import datetime  # noqa: TC003

from pydantic import BaseModel, ConfigDict, Field

from src.type_definitions.common import JSONObject  # noqa: TC001


class VariableDefinition(BaseModel):
    """Domain representation of a kernel variable definition."""

    model_config = ConfigDict(from_attributes=True, frozen=True)

    id: str = Field(..., min_length=1, max_length=64)
    canonical_name: str = Field(..., min_length=1, max_length=128)
    display_name: str = Field(..., min_length=1, max_length=255)
    data_type: str = Field(..., min_length=1, max_length=32)
    preferred_unit: str | None = Field(None, max_length=64)
    constraints: JSONObject = Field(default_factory=dict)
    domain_context: str = Field(default="general", min_length=1, max_length=64)
    sensitivity: str = Field(default="INTERNAL", min_length=1, max_length=32)
    description: str | None = None
    created_at: datetime
    updated_at: datetime


class TransformRegistry(BaseModel):
    """Domain representation of a safe unit/format transformation."""

    model_config = ConfigDict(from_attributes=True, frozen=True)

    id: str = Field(..., min_length=1, max_length=64)
    input_unit: str = Field(..., min_length=1, max_length=64)
    output_unit: str = Field(..., min_length=1, max_length=64)
    implementation_ref: str = Field(..., min_length=1, max_length=255)
    status: str = Field(..., min_length=1, max_length=32)
    created_at: datetime
    updated_at: datetime


class EntityResolutionPolicy(BaseModel):
    """Domain representation of an entity deduplication policy."""

    model_config = ConfigDict(from_attributes=True, frozen=True)

    entity_type: str = Field(..., min_length=1, max_length=64)
    policy_strategy: str = Field(..., min_length=1, max_length=32)
    required_anchors: list[str] = Field(default_factory=list)
    auto_merge_threshold: float = Field(default=1.0, ge=0.0)
    created_at: datetime
    updated_at: datetime


class RelationConstraint(BaseModel):
    """Domain representation of an allowed (source_type, relation_type, target_type) triple."""

    model_config = ConfigDict(from_attributes=True, frozen=True)

    id: int
    source_type: str = Field(..., min_length=1, max_length=64)
    relation_type: str = Field(..., min_length=1, max_length=64)
    target_type: str = Field(..., min_length=1, max_length=64)
    is_allowed: bool
    requires_evidence: bool
    created_at: datetime
    updated_at: datetime


__all__ = [
    "EntityResolutionPolicy",
    "RelationConstraint",
    "TransformRegistry",
    "VariableDefinition",
]
