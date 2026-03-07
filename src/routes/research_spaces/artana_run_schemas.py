"""Schemas for Artana observability routes."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from src.type_definitions.common import JSONObject


class ArtanaRunEvent(BaseModel):
    """Normalized recent Artana event."""

    model_config = ConfigDict(strict=False)

    seq: int
    event_id: str
    event_type: str
    timestamp: datetime
    parent_step_key: str | None = None
    step_key: str | None = None
    tool_name: str | None = None
    tool_outcome: str | None = None
    payload: JSONObject = Field(default_factory=dict)


class ArtanaRunSummary(BaseModel):
    """Latest summary for one Artana run-summary channel."""

    model_config = ConfigDict(strict=False)

    summary_type: str
    timestamp: datetime
    step_key: str | None = None
    payload: JSONObject = Field(default_factory=dict)


class ArtanaRunAlert(BaseModel):
    """Derived observability alert for a run."""

    model_config = ConfigDict(strict=False)

    code: str
    severity: str
    title: str
    description: str
    triggered_at: datetime | None = None
    metadata: JSONObject = Field(default_factory=dict)


class ArtanaLinkedRecordSummary(BaseModel):
    """MED13 record linked to one Artana run."""

    model_config = ConfigDict(strict=False)

    record_type: str
    record_id: str
    research_space_id: str | None = None
    source_id: str | None = None
    document_id: str | None = None
    source_type: str | None = None
    status: str | None = None
    label: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    metadata: JSONObject = Field(default_factory=dict)


class ArtanaRawTableSummary(BaseModel):
    """Admin-only sample of legacy Artana state tables."""

    model_config = ConfigDict(strict=False)

    table_name: str
    row_count: int = Field(default=0, ge=0)
    latest_created_at: datetime | None = None
    sample_rows: list[JSONObject] = Field(default_factory=list)


class ArtanaRunTraceResponse(BaseModel):
    """Full observability payload for one Artana run."""

    model_config = ConfigDict(strict=False)

    requested_run_id: str
    run_id: str
    candidate_run_ids: list[str] = Field(default_factory=list)
    space_id: str
    source_ids: list[str] = Field(default_factory=list)
    source_types: list[str] = Field(default_factory=list)
    status: str
    last_event_seq: int | None = None
    last_event_type: str | None = None
    progress_percent: int | None = None
    current_stage: str | None = None
    completed_stages: list[str] = Field(default_factory=list)
    started_at: datetime | None = None
    updated_at: datetime | None = None
    eta_seconds: int | None = None
    blocked_on: str | None = None
    failure_reason: str | None = None
    error_category: str | None = None
    explain: JSONObject = Field(default_factory=dict)
    alerts: list[ArtanaRunAlert] = Field(default_factory=list)
    events: list[ArtanaRunEvent] = Field(default_factory=list)
    summaries: list[ArtanaRunSummary] = Field(default_factory=list)
    linked_records: list[ArtanaLinkedRecordSummary] = Field(default_factory=list)
    raw_tables: list[ArtanaRawTableSummary] | None = None


class ArtanaRunListItem(BaseModel):
    """One row in the admin Artana run explorer."""

    model_config = ConfigDict(strict=False)

    run_id: str
    space_id: str
    source_ids: list[str] = Field(default_factory=list)
    source_type: str | None = None
    status: str
    current_stage: str | None = None
    updated_at: datetime | None = None
    started_at: datetime | None = None
    last_event_type: str | None = None
    alert_count: int = Field(default=0, ge=0)
    alert_codes: list[str] = Field(default_factory=list)


class ArtanaRunListCounters(BaseModel):
    """Aggregate alert and lifecycle counters for the admin explorer."""

    model_config = ConfigDict(strict=False)

    running: int = Field(default=0, ge=0)
    failed: int = Field(default=0, ge=0)
    stuck: int = Field(default=0, ge=0)
    drift_detected: int = Field(default=0, ge=0)
    budget_warning: int = Field(default=0, ge=0)
    tool_unknown_outcome: int = Field(default=0, ge=0)


class ArtanaRunListResponse(BaseModel):
    """Paginated admin explorer response."""

    model_config = ConfigDict(strict=False)

    runs: list[ArtanaRunListItem] = Field(default_factory=list)
    total: int = Field(default=0, ge=0)
    page: int = Field(default=1, ge=1)
    per_page: int = Field(default=25, ge=1)
    counters: ArtanaRunListCounters = Field(default_factory=ArtanaRunListCounters)


__all__ = [
    "ArtanaLinkedRecordSummary",
    "ArtanaRawTableSummary",
    "ArtanaRunAlert",
    "ArtanaRunEvent",
    "ArtanaRunListCounters",
    "ArtanaRunListItem",
    "ArtanaRunListResponse",
    "ArtanaRunSummary",
    "ArtanaRunTraceResponse",
]
