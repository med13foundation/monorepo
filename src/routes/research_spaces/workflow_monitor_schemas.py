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


class PipelineRunSummaryEnvelopeResponse(BaseModel):
    """Summary envelope for one pipeline run."""

    model_config = ConfigDict(strict=False)

    source_id: UUID
    run_id: str
    generated_at: datetime
    run: JSONObject = Field(default_factory=dict)


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
    paper_candidates: list[JSONObject] = Field(default_factory=list)
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
    event_type: str | None = None
    stage: str | None = None
    status: str | None = None
    level: str | None = None
    scope_kind: str | None = None
    scope_id: str | None = None
    agent_kind: str | None = None
    agent_run_id: str | None = None
    error_code: str | None = None
    message: str
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_ms: int | None = Field(default=None, ge=0)
    queue_wait_ms: int | None = Field(default=None, ge=0)
    timeout_budget_ms: int | None = Field(default=None, ge=0)
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


class SourceWorkflowDocumentTraceResponse(BaseModel):
    """Document-scoped pipeline trace for one run."""

    model_config = ConfigDict(strict=False)

    source_id: UUID
    run_id: str
    document_id: UUID
    generated_at: datetime
    document: JSONObject | None = None
    extraction_rows: list[JSONObject] = Field(default_factory=list)
    events: list[SourceWorkflowEvent] = Field(default_factory=list)


class SourceWorkflowQueryTraceResponse(BaseModel):
    """Query-generation trace for one pipeline run."""

    model_config = ConfigDict(strict=False)

    source_id: UUID
    run_id: str
    generated_at: datetime
    base_query: str | None = None
    executed_query: str | None = None
    query_generation: JSONObject = Field(default_factory=dict)
    events: list[SourceWorkflowEvent] = Field(default_factory=list)


class PipelineRunTimingSummaryResponse(BaseModel):
    """Timing summary for one pipeline run."""

    model_config = ConfigDict(strict=False)

    source_id: UUID
    run_id: str
    generated_at: datetime
    timing_summary: JSONObject = Field(default_factory=dict)


class PipelineRunCostSummaryResponse(BaseModel):
    """Direct AI/tool cost summary for one pipeline run."""

    model_config = ConfigDict(strict=False)

    source_id: UUID
    run_id: str
    generated_at: datetime
    cost_summary: JSONObject = Field(default_factory=dict)


class PipelineRunCostReportItem(BaseModel):
    """One row in a pipeline run cost report."""

    model_config = ConfigDict(strict=False)

    run_id: str
    source_id: UUID
    research_space_id: UUID
    source_name: str | None = None
    source_type: str | None = None
    status: str | None = None
    run_owner_user_id: str | None = None
    run_owner_source: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    total_duration_ms: int | None = Field(default=None, ge=0)
    total_cost_usd: float = Field(default=0.0, ge=0.0)
    extracted_documents: int = Field(default=0, ge=0)
    persisted_relations: int = Field(default=0, ge=0)


class PipelineRunCostReportResponse(BaseModel):
    """Pipeline run cost report for a source or user slice."""

    model_config = ConfigDict(strict=False)

    generated_at: datetime
    items: list[PipelineRunCostReportItem] = Field(default_factory=list)
    total: int = 0


class PipelineRunComparisonResponse(BaseModel):
    """High-level comparison between two source pipeline runs."""

    model_config = ConfigDict(strict=False)

    source_id: UUID
    run_a_id: str
    run_b_id: str
    generated_at: datetime
    run_a: JSONObject = Field(default_factory=dict)
    run_b: JSONObject = Field(default_factory=dict)
    delta: JSONObject = Field(default_factory=dict)


__all__ = [
    "ArtanaStageProgressSnapshot",
    "PipelineRunSummaryEnvelopeResponse",
    "PipelineRunComparisonResponse",
    "PipelineRunCostReportItem",
    "PipelineRunCostReportResponse",
    "PipelineRunCostSummaryResponse",
    "PipelineRunTimingSummaryResponse",
    "SourcePipelineRunListResponse",
    "SourceWorkflowDocumentTraceResponse",
    "SourceWorkflowEvent",
    "SourceWorkflowEventListResponse",
    "SourceWorkflowMonitorResponse",
    "SourceWorkflowQueryTraceResponse",
]
