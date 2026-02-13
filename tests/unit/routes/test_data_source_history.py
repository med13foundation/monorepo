"""Tests for data source ingestion history response shaping."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from src.domain.entities.ingestion_job import (
    IngestionJob,
    IngestionStatus,
    IngestionTrigger,
    JobMetrics,
)
from src.domain.value_objects.provenance import DataSource, Provenance
from src.routes.admin_routes.data_sources.history import _job_to_response

if TYPE_CHECKING:
    from src.type_definitions.common import JSONObject


def _build_job(
    *,
    metadata: JSONObject,
) -> IngestionJob:
    return IngestionJob(
        id=uuid4(),
        source_id=uuid4(),
        trigger=IngestionTrigger.SCHEDULED,
        triggered_by=None,
        triggered_at=datetime.now(UTC),
        status=IngestionStatus.COMPLETED,
        started_at=datetime.now(UTC),
        completed_at=datetime.now(UTC),
        metrics=JobMetrics(
            records_processed=12,
            records_failed=1,
            records_skipped=3,
            bytes_processed=1024,
            api_calls_made=4,
            duration_seconds=None,
            records_per_second=None,
        ),
        provenance=Provenance(
            source=DataSource.COMPUTED,
            source_version=None,
            source_url=None,
            acquired_by="test-suite",
            processing_steps=("scheduled_ingestion",),
            quality_score=None,
        ),
        metadata=metadata,
        source_config_snapshot={},
    )


def test_job_to_response_extracts_idempotency_metadata() -> None:
    job = _build_job(
        metadata={
            "executed_query": "MED13 query",
            "idempotency": {
                "query_signature": "abc123",
                "checkpoint_before": {"cursor": "page-1"},
                "checkpoint_after": {"cursor": "page-2"},
                "new_records": 2,
                "updated_records": 1,
                "unchanged_records": 5,
                "skipped_records": 5,
            },
        },
    )

    response = _job_to_response(job)

    assert response.executed_query == "MED13 query"
    assert response.idempotency is not None
    assert response.idempotency.query_signature == "abc123"
    assert response.idempotency.checkpoint_after == {"cursor": "page-2"}
    assert response.idempotency.unchanged_records == 5


def test_job_to_response_ignores_invalid_idempotency_payload() -> None:
    job = _build_job(
        metadata={
            "executed_query": "MED13 query",
            "idempotency": {"new_records": "invalid"},
        },
    )

    response = _job_to_response(job)

    assert response.executed_query == "MED13 query"
    assert response.idempotency is None


def test_job_to_response_parses_typed_metadata_envelope() -> None:
    job = _build_job(
        metadata={
            "executed_query": "MED13 query",
            "query_generation": {
                "run_id": "run-123",
                "model": "gpt-5",
                "decision": "generated",
                "confidence": 0.91,
            },
            "idempotency": {
                "query_signature": "abc123",
                "checkpoint_kind": "cursor",
                "checkpoint_before": {"retstart": 0},
                "checkpoint_after": {"retstart": 10},
                "new_records": 3,
                "updated_records": 1,
                "unchanged_records": 6,
                "skipped_records": 6,
            },
            "extraction_queue": {
                "requested": 4,
                "queued": 4,
                "skipped": 0,
                "version": 1,
            },
            "extraction_run": {
                "source_id": "source-1",
                "ingestion_job_id": "job-1",
                "requested": 4,
                "processed": 4,
                "completed": 3,
                "skipped": 1,
                "failed": 0,
                "started_at": "2026-02-13T10:00:00+00:00",
                "completed_at": "2026-02-13T10:01:00+00:00",
            },
        },
    )

    response = _job_to_response(job)

    assert response.metadata_typed is not None
    assert response.query_generation is not None
    assert response.query_generation.decision == "generated"
    assert response.idempotency is not None
    assert response.idempotency.checkpoint_kind == "cursor"
    assert response.metadata_typed.extraction_queue is not None
    assert response.metadata_typed.extraction_queue.queued == 4
