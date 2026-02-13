"""Pydantic request and response schemas for admin data source routes."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from src.domain.entities.ingestion_job import IngestionStatus, IngestionTrigger
from src.domain.entities.user_data_source import (
    IngestionSchedule,
    QualityMetrics,
    ScheduleFrequency,
    SourceConfiguration,
    SourceStatus,
    SourceType,
)
from src.models.api.common import PaginatedResponse
from src.type_definitions.common import JSONObject
from src.type_definitions.data_sources import (
    IngestionIdempotencyMetadata,
    IngestionJobMetadata,
    IngestionQueryGenerationMetadata,
)


class CreateDataSourceRequest(BaseModel):
    """Request payload for creating a data source."""

    name: str = Field(..., min_length=1, max_length=100)
    description: str | None = Field(None, max_length=500)
    source_type: SourceType
    template_id: UUID | None = None
    config: SourceConfiguration = Field(
        ...,
        description="Data source configuration",
    )
    ingestion_schedule: IngestionSchedule | None = Field(
        None,
        description="Ingestion schedule configuration",
    )


class UpdateDataSourceRequest(BaseModel):
    """Request payload for updating a data source."""

    name: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = Field(None, max_length=500)
    status: SourceStatus | None = None
    config: SourceConfiguration | None = Field(
        None,
        description="Updated data source configuration",
    )
    ingestion_schedule: IngestionSchedule | None = Field(
        None,
        description="Updated ingestion schedule",
    )


class DataSourceResponse(BaseModel):
    """Response model for data source information."""

    id: UUID
    owner_id: UUID
    name: str
    description: str | None
    source_type: SourceType
    status: SourceStatus
    config: SourceConfiguration = Field(validation_alias="configuration")
    template_id: UUID | None
    ingestion_schedule: IngestionSchedule | None
    quality_metrics: QualityMetrics | None
    last_ingested_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# Use standardized pagination response
DataSourceListResponse = PaginatedResponse[DataSourceResponse]


class ScheduleConfigurationRequest(BaseModel):
    """Request payload for configuring an ingestion schedule."""

    enabled: bool = True
    frequency: ScheduleFrequency = ScheduleFrequency.DAILY
    start_time: datetime | None = None
    timezone: str = "UTC"
    cron_expression: str | None = None


class ScheduledJobResponse(BaseModel):
    """Response payload for scheduled job metadata."""

    job_id: str
    source_id: UUID
    next_run_at: datetime
    frequency: ScheduleFrequency
    cron_expression: str | None = None


class ScheduleConfigurationResponse(BaseModel):
    """Response payload after configuring ingestion scheduling."""

    ingestion_schedule: IngestionSchedule
    scheduled_job: ScheduledJobResponse | None = None


class IngestionRunResponse(BaseModel):
    """Response for manual ingestion trigger runs."""

    source_id: UUID
    fetched_records: int
    parsed_publications: int
    created_publications: int
    updated_publications: int
    executed_query: str | None = None


class IngestionJobResponse(BaseModel):
    """Response describing a single ingestion job run."""

    id: UUID
    status: IngestionStatus
    trigger: IngestionTrigger
    started_at: str | None
    completed_at: str | None
    records_processed: int
    records_failed: int
    records_skipped: int
    bytes_processed: int
    executed_query: str | None = None
    query_generation: IngestionQueryGenerationMetadata | None = None
    idempotency: IngestionIdempotencyMetadata | None = None
    metadata_typed: IngestionJobMetadata | None = None
    metadata: JSONObject | None = None


class IngestionJobHistoryResponse(BaseModel):
    """Collection of ingestion jobs for a given source."""

    source_id: UUID
    items: list[IngestionJobResponse]


__all__ = [
    "CreateDataSourceRequest",
    "DataSourceListResponse",
    "DataSourceResponse",
    "IngestionRunResponse",
    "ScheduleConfigurationRequest",
    "ScheduleConfigurationResponse",
    "ScheduledJobResponse",
    "IngestionJobResponse",
    "IngestionJobHistoryResponse",
    "UpdateDataSourceRequest",
]
