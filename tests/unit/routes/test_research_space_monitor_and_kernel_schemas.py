"""Schema contract tests for workflow monitor and kernel provenance routes."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from src.domain.entities.kernel.provenance import KernelProvenanceRecord
from src.routes.research_spaces.kernel_schemas import KernelProvenanceResponse
from src.routes.research_spaces.workflow_monitor_schemas import (
    SourceWorkflowEventListResponse,
    SourceWorkflowMonitorResponse,
)


def test_kernel_provenance_response_accepts_non_uuid_extraction_run_id() -> None:
    now = datetime.now(UTC)
    record = KernelProvenanceRecord(
        id=uuid4(),
        research_space_id=uuid4(),
        source_type="AI_EXTRACTION",
        source_ref="test://source",
        extraction_run_id="extract:pubmed:sha256:abc123",
        mapping_method="llm",
        mapping_confidence=0.91,
        agent_model="gpt-5",
        raw_input={"source": "pubmed"},
        created_at=now,
        updated_at=now,
    )

    response = KernelProvenanceResponse.from_model(record)

    assert response.extraction_run_id == "extract:pubmed:sha256:abc123"


def test_workflow_monitor_response_validates_artana_progress_payload() -> None:
    now = datetime.now(UTC)
    payload = SourceWorkflowMonitorResponse.model_validate(
        {
            "source_snapshot": {},
            "last_run": None,
            "pipeline_runs": [],
            "documents": [],
            "document_status_counts": {},
            "extraction_queue": [],
            "extraction_queue_status_counts": {},
            "publication_extractions": [],
            "publication_extraction_status_counts": {},
            "relation_review": {},
            "graph_summary": None,
            "operational_counters": {},
            "artana_progress": {
                "extraction": {
                    "stage": "extraction",
                    "run_id": "extract:pubmed:sha256:abc123",
                    "status": "running",
                    "percent": 67,
                    "current_stage": "extraction.step",
                    "completed_stages": ["ingestion", "enrichment"],
                    "started_at": now,
                    "updated_at": now,
                    "eta_seconds": 120,
                    "candidate_run_ids": ["extract:pubmed:sha256:abc123"],
                },
            },
            "warnings": [],
        },
    )

    extraction = payload.artana_progress["extraction"]
    assert extraction.run_id == "extract:pubmed:sha256:abc123"
    assert extraction.percent == 67
    assert extraction.status == "running"


def test_workflow_monitor_response_accepts_iso_timestamps_in_artana_progress() -> None:
    now = datetime.now(UTC)
    payload = SourceWorkflowMonitorResponse.model_validate(
        {
            "source_snapshot": {},
            "last_run": None,
            "pipeline_runs": [],
            "documents": [],
            "document_status_counts": {},
            "extraction_queue": [],
            "extraction_queue_status_counts": {},
            "publication_extractions": [],
            "publication_extraction_status_counts": {},
            "relation_review": {},
            "graph_summary": None,
            "operational_counters": {},
            "artana_progress": {
                "pipeline": {
                    "stage": "pipeline",
                    "run_id": "pipeline:run:abc123",
                    "status": "running",
                    "percent": 12,
                    "current_stage": "ingestion.fetch",
                    "completed_stages": [],
                    "started_at": now.isoformat(),
                    "updated_at": now.isoformat(),
                    "eta_seconds": 90,
                    "candidate_run_ids": ["pipeline:run:abc123"],
                },
            },
            "warnings": [],
        },
    )

    pipeline = payload.artana_progress["pipeline"]
    assert pipeline.started_at == now
    assert pipeline.updated_at == now


def test_workflow_events_response_accepts_stringified_uuid_and_timestamps() -> None:
    source_id = uuid4()
    now = datetime.now(UTC)
    payload = SourceWorkflowEventListResponse.model_validate(
        {
            "source_id": str(source_id),
            "run_id": "pipeline:run:abc123",
            "generated_at": now.isoformat(),
            "events": [
                {
                    "event_id": "run:pipeline:run:abc123",
                    "source_id": str(source_id),
                    "run_id": "pipeline:run:abc123",
                    "occurred_at": now.isoformat(),
                    "category": "run",
                    "stage": None,
                    "status": "running",
                    "message": "Pipeline run status updated.",
                    "payload": {},
                },
            ],
            "total": 1,
            "has_more": False,
        },
    )

    assert payload.source_id == source_id
    assert payload.generated_at == now
    assert payload.events[0].source_id == source_id
    assert payload.events[0].occurred_at == now
