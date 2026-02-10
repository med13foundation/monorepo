"""
Kernel provenance domain entity.

This is the kernel-level provenance table record (how data entered the system),
which is distinct from the general-purpose value object provenance used for
packaging/lineage of MED13 entities.
"""

from __future__ import annotations

from datetime import datetime  # noqa: TC003
from uuid import UUID  # noqa: TC003

from pydantic import BaseModel, ConfigDict, Field

from src.type_definitions.common import JSONObject  # noqa: TC001


class KernelProvenanceRecord(BaseModel):
    """Domain representation of a kernel provenance record."""

    model_config = ConfigDict(from_attributes=True, frozen=True)

    id: UUID
    research_space_id: UUID
    source_type: str = Field(..., min_length=1, max_length=64)
    source_ref: str | None = Field(None, max_length=1024)
    extraction_run_id: UUID | None = None
    mapping_method: str | None = Field(None, max_length=64)
    mapping_confidence: float | None = Field(None, ge=0.0, le=1.0)
    agent_model: str | None = Field(None, max_length=128)
    raw_input: JSONObject | None = None

    created_at: datetime
    updated_at: datetime


__all__ = ["KernelProvenanceRecord"]
