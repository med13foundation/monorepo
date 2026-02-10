"""Pydantic schemas for kernel ingestion routes."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from src.type_definitions.common import JSONObject


class KernelIngestRecordRequest(BaseModel):
    """Single raw record for kernel ingestion."""

    model_config = ConfigDict(strict=True)

    source_id: str = Field(..., min_length=1, max_length=256)
    data: JSONObject
    metadata: JSONObject = Field(default_factory=dict)


class KernelIngestRequest(BaseModel):
    """Batch ingestion request."""

    model_config = ConfigDict(strict=True)

    entity_type: str | None = Field(
        default=None,
        description="If provided, applied to any record missing metadata.entity_type.",
    )
    record_type: str | None = Field(
        default=None,
        description="Optional record type (e.g. 'pubmed'); applied to records missing metadata.type.",
    )
    records: list[KernelIngestRecordRequest] = Field(..., min_length=1, max_length=200)


class KernelIngestResponse(BaseModel):
    """Ingestion result summary."""

    model_config = ConfigDict(strict=True)

    success: bool
    entities_created: int
    observations_created: int
    errors: list[str]


__all__ = [
    "KernelIngestRecordRequest",
    "KernelIngestRequest",
    "KernelIngestResponse",
]
