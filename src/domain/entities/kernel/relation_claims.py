"""Kernel relation-claim domain entities."""

from __future__ import annotations

from datetime import datetime  # noqa: TC003
from typing import Literal
from uuid import UUID  # noqa: TC003

from pydantic import BaseModel, ConfigDict, Field

from src.type_definitions.common import JSONObject  # noqa: TC001

RelationClaimValidationState = Literal[
    "ALLOWED",
    "FORBIDDEN",
    "UNDEFINED",
    "INVALID_COMPONENTS",
    "ENDPOINT_UNRESOLVED",
    "SELF_LOOP",
]
RelationClaimPersistability = Literal["PERSISTABLE", "NON_PERSISTABLE"]
RelationClaimStatus = Literal["OPEN", "NEEDS_MAPPING", "REJECTED", "RESOLVED"]


class KernelRelationClaim(BaseModel):
    """One extracted relation candidate captured for curation."""

    model_config = ConfigDict(from_attributes=True, frozen=True)

    id: UUID
    research_space_id: UUID
    source_document_id: UUID | None = None
    agent_run_id: str | None = Field(default=None, max_length=255)
    source_type: str = Field(..., min_length=1, max_length=64)
    relation_type: str = Field(..., min_length=1, max_length=64)
    target_type: str = Field(..., min_length=1, max_length=64)
    source_label: str | None = Field(default=None, max_length=512)
    target_label: str | None = Field(default=None, max_length=512)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    validation_state: RelationClaimValidationState
    validation_reason: str | None = None
    persistability: RelationClaimPersistability
    claim_status: RelationClaimStatus = "OPEN"
    linked_relation_id: UUID | None = None
    metadata_payload: JSONObject = Field(default_factory=dict)
    triaged_by: UUID | None = None
    triaged_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


__all__ = [
    "KernelRelationClaim",
    "RelationClaimPersistability",
    "RelationClaimStatus",
    "RelationClaimValidationState",
]
