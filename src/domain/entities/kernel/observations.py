"""
Kernel observation domain entity (typed facts).

This represents the kernel observation rows as a domain object, without ORM
dependencies.
"""

from __future__ import annotations

from datetime import datetime  # noqa: TC003
from uuid import UUID  # noqa: TC003

from pydantic import BaseModel, ConfigDict, Field

from src.type_definitions.common import JSONValue  # noqa: TC001


class KernelObservation(BaseModel):
    """Domain representation of a kernel observation (typed fact)."""

    model_config = ConfigDict(from_attributes=True, frozen=True)

    id: UUID
    research_space_id: UUID
    subject_id: UUID
    variable_id: str = Field(..., min_length=1, max_length=64)

    value_numeric: float | None = None
    value_text: str | None = None
    value_date: datetime | None = None
    value_coded: str | None = None
    value_boolean: bool | None = None
    value_json: JSONValue | None = None

    unit: str | None = Field(None, max_length=64)
    observed_at: datetime | None = None
    provenance_id: UUID | None = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)

    created_at: datetime
    updated_at: datetime


__all__ = ["KernelObservation"]
