"""Schemas for source workflow monitoring routes."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from src.type_definitions.common import JSONObject


class SourcePipelineRunListResponse(BaseModel):
    """Pipeline run list for one source."""

    model_config = ConfigDict(strict=True)

    source_id: UUID
    runs: list[JSONObject] = Field(default_factory=list)
    total: int = 0


class ArtanaStageProgressSnapshot(BaseModel):
    """Per-stage Artana run progress snapshot."""

    model_config = ConfigDict(strict=False)

    stage: str
    run_id: str | None = None
    status: str | None = None
    percent: int | None = Field(default=None, ge=0, le=100)
    current_stage: str | None = None
    completed_stages: list[str] = Field(default_factory=list)
    started_at: datetime | None = None
    updated_at: datetime | None = None
    eta_seconds: int | None = None
    candidate_run_ids: list[str] = Field(default_factory=list)


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
    artana_progress: dict[str, ArtanaStageProgressSnapshot] = Field(
        default_factory=dict,
    )
    warnings: list[str] = Field(default_factory=list)


WorkflowEventCategory = Literal[
    "run",
    "stage",
    "document",
    "queue",
    "extraction",
    "review",
    "graph",
]


class SourceWorkflowEvent(BaseModel):
    """One timeline event emitted by the source workflow monitor."""

    model_config = ConfigDict(strict=False)

    event_id: str
    source_id: UUID
    run_id: str | None = None
    occurred_at: datetime
    category: WorkflowEventCategory
    stage: str | None = None
    status: str | None = None
    message: str
    payload: JSONObject = Field(default_factory=dict)


class SourceWorkflowEventListResponse(BaseModel):
    """Detailed monitor events for one source (optionally one run)."""

    model_config = ConfigDict(strict=False)

    source_id: UUID
    run_id: str | None = None
    generated_at: datetime
    events: list[SourceWorkflowEvent] = Field(default_factory=list)
    total: int = 0
    has_more: bool = False


__all__ = [
    "ArtanaStageProgressSnapshot",
    "SourcePipelineRunListResponse",
    "SourceWorkflowEvent",
    "SourceWorkflowEventListResponse",
    "SourceWorkflowMonitorResponse",
]
