"""Ingestion history endpoints for admin data sources."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import ValidationError

from src.domain.entities.ingestion_job import IngestionJob
from src.domain.repositories.ingestion_job_repository import IngestionJobRepository
from src.routes.admin_routes.data_sources.schemas import (
    IngestionJobHistoryResponse,
    IngestionJobResponse,
)
from src.routes.admin_routes.dependencies import get_ingestion_job_repository
from src.type_definitions.data_sources import (
    IngestionIdempotencyMetadata,
    IngestionJobMetadata,
    IngestionQueryGenerationMetadata,
)

router = APIRouter()


def _extract_executed_query(metadata: object) -> str | None:
    if not isinstance(metadata, dict):
        return None
    executed_query = metadata.get("executed_query")
    return executed_query if isinstance(executed_query, str) else None


def _extract_query_generation(
    metadata: object,
) -> IngestionQueryGenerationMetadata | None:
    if not isinstance(metadata, dict):
        return None
    query_generation_raw = metadata.get("query_generation")
    if not isinstance(query_generation_raw, dict):
        return None
    try:
        return IngestionQueryGenerationMetadata.model_validate(query_generation_raw)
    except ValidationError:
        return None


def _extract_idempotency(metadata: object) -> IngestionIdempotencyMetadata | None:
    if not isinstance(metadata, dict):
        return None
    idempotency_raw = metadata.get("idempotency")
    if not isinstance(idempotency_raw, dict):
        return None
    try:
        return IngestionIdempotencyMetadata.model_validate(idempotency_raw)
    except ValidationError:
        return None


def _job_to_response(job: IngestionJob) -> IngestionJobResponse:
    metrics = job.metrics
    metadata = dict(job.metadata or {})
    typed_metadata = IngestionJobMetadata.parse_optional(metadata)
    executed_query = (
        typed_metadata.executed_query
        if typed_metadata is not None
        else _extract_executed_query(metadata)
    )
    query_generation = (
        typed_metadata.query_generation
        if typed_metadata is not None
        else _extract_query_generation(metadata)
    )
    idempotency = (
        typed_metadata.idempotency
        if typed_metadata is not None
        else _extract_idempotency(metadata)
    )
    return IngestionJobResponse(
        id=job.id,
        status=job.status,
        trigger=job.trigger,
        started_at=job.started_at.isoformat() if job.started_at else None,
        completed_at=job.completed_at.isoformat() if job.completed_at else None,
        records_processed=metrics.records_processed,
        records_failed=metrics.records_failed,
        records_skipped=metrics.records_skipped,
        bytes_processed=metrics.bytes_processed,
        executed_query=executed_query,
        query_generation=query_generation,
        idempotency=idempotency,
        metadata_typed=typed_metadata,
        metadata=metadata,
    )


@router.get(
    "/{source_id}/ingestion-jobs",
    response_model=IngestionJobHistoryResponse,
    summary="List recent ingestion jobs",
    description="Return recent ingestion job executions for the specified data source.",
)
def list_ingestion_jobs(
    source_id: UUID,
    limit: int = Query(
        10,
        ge=1,
        le=100,
        description="Maximum number of jobs to return",
    ),
    repository: IngestionJobRepository = Depends(get_ingestion_job_repository),
) -> IngestionJobHistoryResponse:
    jobs = repository.find_by_source(source_id, limit=limit)
    return IngestionJobHistoryResponse(
        source_id=source_id,
        items=[_job_to_response(job) for job in jobs],
    )


__all__ = ["router"]
