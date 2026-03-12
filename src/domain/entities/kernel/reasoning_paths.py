"""Derived reasoning-path domain entities."""

from __future__ import annotations

from datetime import datetime  # noqa: TC003
from typing import Literal
from uuid import UUID  # noqa: TC003

from pydantic import BaseModel, ConfigDict, Field

from src.type_definitions.common import JSONObject  # noqa: TC001

ReasoningPathKind = Literal["MECHANISM"]
ReasoningPathStatus = Literal["ACTIVE", "STALE"]


class KernelReasoningPath(BaseModel):
    """One persisted derived reasoning path."""

    model_config = ConfigDict(from_attributes=True, frozen=True)

    id: UUID
    research_space_id: UUID
    path_kind: ReasoningPathKind = "MECHANISM"
    status: ReasoningPathStatus = "ACTIVE"
    start_entity_id: UUID
    end_entity_id: UUID
    root_claim_id: UUID
    path_length: int = Field(ge=1, le=32)
    confidence: float = Field(ge=0.0, le=1.0)
    path_signature_hash: str = Field(min_length=32, max_length=128)
    generated_by: str | None = Field(default=None, max_length=255)
    generated_at: datetime
    metadata_payload: JSONObject = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class KernelReasoningPathStep(BaseModel):
    """One ordered step inside a persisted reasoning path."""

    model_config = ConfigDict(from_attributes=True, frozen=True)

    id: UUID
    path_id: UUID
    step_index: int = Field(ge=0, le=255)
    source_claim_id: UUID
    target_claim_id: UUID
    claim_relation_id: UUID
    canonical_relation_id: UUID | None = None
    metadata_payload: JSONObject = Field(default_factory=dict)
    created_at: datetime


__all__ = [
    "KernelReasoningPath",
    "KernelReasoningPathStep",
    "ReasoningPathKind",
    "ReasoningPathStatus",
]
