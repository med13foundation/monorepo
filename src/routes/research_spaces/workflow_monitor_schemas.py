"""Schemas for source workflow monitoring routes."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from src.type_definitions.common import JSONObject


class SourcePipelineRunListResponse(BaseModel):
    """Pipeline run list for one source."""

    model_config = ConfigDict(strict=True)

    source_id: UUID
    runs: list[JSONObject] = Field(default_factory=list)
    total: int = 0


class SourceWorkflowMonitorResponse(BaseModel):
    """Composite source workflow monitor payload."""

    model_config = ConfigDict(strict=True)

    source_snapshot: JSONObject
    last_run: JSONObject | None = None
    pipeline_runs: list[JSONObject] = Field(default_factory=list)
    documents: list[JSONObject] = Field(default_factory=list)
    document_status_counts: dict[str, int] = Field(default_factory=dict)
    extraction_queue: list[JSONObject] = Field(default_factory=list)
    extraction_queue_status_counts: dict[str, int] = Field(default_factory=dict)
    publication_extractions: list[JSONObject] = Field(default_factory=list)
    publication_extraction_status_counts: dict[str, int] = Field(default_factory=dict)
    relation_review: JSONObject = Field(default_factory=dict)
    graph_summary: JSONObject | None = None
    operational_counters: JSONObject = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


__all__ = [
    "SourcePipelineRunListResponse",
    "SourceWorkflowMonitorResponse",
]
