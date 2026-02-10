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

    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    evidence_summary: str | None = None
    evidence_tier: str | None = Field(None, max_length=32)
    curation_status: str = Field(default="DRAFT", min_length=1, max_length=32)

    provenance_id: UUID | None = None
    reviewed_by: UUID | None = None
    reviewed_at: datetime | None = None

    created_at: datetime
    updated_at: datetime


__all__ = ["KernelRelation"]
