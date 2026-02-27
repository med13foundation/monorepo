"""
Kernel entity domain entities (graph nodes + identifiers).

These correspond to the kernel entity tables but intentionally avoid ORM types.
"""

from __future__ import annotations

from datetime import datetime  # noqa: TC003
from uuid import UUID  # noqa: TC003

from pydantic import BaseModel, ConfigDict, Field

from src.type_definitions.common import JSONObject  # noqa: TC001


class KernelEntity(BaseModel):
    """Domain representation of a kernel entity (graph node)."""

    model_config = ConfigDict(
        from_attributes=True,
        frozen=True,
        populate_by_name=True,
    )

    id: UUID
    research_space_id: UUID
    entity_type: str = Field(..., min_length=1, max_length=64)
    display_label: str | None = Field(None, max_length=512)
    metadata: JSONObject = Field(default_factory=dict, alias="metadata_payload")
    created_at: datetime
    updated_at: datetime


class KernelEntityIdentifier(BaseModel):
    """Domain representation of an identifier attached to a kernel entity."""

    model_config = ConfigDict(from_attributes=True, frozen=True)

    id: int
    entity_id: UUID
    namespace: str = Field(..., min_length=1, max_length=64)
    identifier_value: str = Field(..., min_length=1, max_length=512)
    identifier_blind_index: str | None = Field(None, max_length=64)
    encryption_key_version: str | None = Field(None, max_length=32)
    blind_index_version: str | None = Field(None, max_length=32)
    sensitivity: str = Field(..., min_length=1, max_length=32)
    created_at: datetime
    updated_at: datetime


__all__ = ["KernelEntity", "KernelEntityIdentifier"]
