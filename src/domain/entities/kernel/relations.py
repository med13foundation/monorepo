"""
Kernel relation domain entity (graph edges).

Represents kernel relations as domain objects without ORM coupling.
"""

from __future__ import annotations

from datetime import datetime  # noqa: TC003
from uuid import UUID  # noqa: TC003

from pydantic import BaseModel, ConfigDict, Field


class KernelRelation(BaseModel):
    """Domain representation of a kernel relation (graph edge)."""

    model_config = ConfigDict(from_attributes=True, frozen=True)

    id: UUID
    research_space_id: UUID
    source_id: UUID
    relation_type: str = Field(..., min_length=1, max_length=64)
    target_id: UUID

    aggregate_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    source_count: int = Field(default=0, ge=0)
    highest_evidence_tier: str | None = Field(None, max_length=32)
    curation_status: str = Field(default="DRAFT", min_length=1, max_length=32)

    provenance_id: UUID | None = None
    reviewed_by: UUID | None = None
    reviewed_at: datetime | None = None

    created_at: datetime
    updated_at: datetime


class KernelRelationEvidence(BaseModel):
    """Domain representation of one supporting evidence row for a relation."""

    model_config = ConfigDict(from_attributes=True, frozen=True)

    id: UUID
    relation_id: UUID
    confidence: float = Field(..., ge=0.0, le=1.0)
    evidence_summary: str | None = None
    evidence_tier: str = Field(..., min_length=1, max_length=32)
    provenance_id: UUID | None = None
    source_document_id: UUID | None = None
    agent_run_id: str | None = Field(default=None, max_length=255)
    created_at: datetime


__all__ = ["KernelRelation", "KernelRelationEvidence"]
