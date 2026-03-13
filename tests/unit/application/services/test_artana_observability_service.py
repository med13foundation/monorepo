"""Unit tests for Artana observability helpers and read models."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from src.application.services.artana_observability_service import (
    ArtanaObservabilityService,
    _has_drift_alert,
    _resolve_budget_warning,
    _resolve_unknown_outcome_alert,
    _RunSnapshotRow,
)
from src.application.services.ports.artana_run_trace_port import (
    ArtanaRunTraceEventRecord,
    ArtanaRunTraceRecord,
    ArtanaRunTraceSummaryRecord,
)
from src.models.database.extraction_queue import (
    ExtractionQueueItemModel,
    ExtractionStatusEnum,
)
from src.models.database.ingestion_job import (
    IngestionJobKindEnum,
    IngestionJobModel,
    IngestionStatusEnum,
    IngestionTriggerEnum,
)
from src.models.database.kernel.provenance import ProvenanceModel
from src.models.database.publication_extraction import (
    ExtractionOutcomeEnum,
    PublicationExtractionModel,
)
from src.models.database.research_space import ResearchSpaceModel
from src.models.database.source_document import SourceDocumentModel
from src.models.database.user import UserModel
from src.models.database.user_data_source import (
    SourceStatusEnum,
    SourceTypeEnum,
    UserDataSourceModel,
)


def _iso_timestamp() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _build_trace_record(
    *,
    run_id: str = "run-1",
    status: str = "running",
    updated_at: datetime | None = None,
    events: tuple[ArtanaRunTraceEventRecord, ...] = (),
    summaries: tuple[ArtanaRunTraceSummaryRecord, ...] = (),
    explain: dict[str, object] | None = None,
    failure_reason: str | None = None,
) -> ArtanaRunTraceRecord:
    now = updated_at or datetime.now(UTC)
    return ArtanaRunTraceRecord(
        run_id=run_id,
        tenant_id="space-1",
        status=status,
        last_event_seq=events[-1].seq if events else None,
        last_event_type=events[-1].event_type if events else None,
        updated_at=now,
        blocked_on=None,
        failure_reason=failure_reason,
        error_category=None,
        progress_percent=50,
        current_stage="extraction",
        completed_stages=("ingestion",),
        started_at=now - timedelta(minutes=5),
        eta_seconds=60,
        explain=explain or {},
        events=events,
        summaries=summaries,
    )


def test_resolve_unknown_outcome_alert_detects_pending_tool_request() -> None:
    now = datetime.now(UTC)
    alert = _resolve_unknown_outcome_alert(
        (
            ArtanaRunTraceEventRecord(
                seq=1,
                event_id="tool-request-1",
                event_type="tool_requested",
                timestamp=now - timedelta(minutes=7),
                parent_step_key=None,
                payload={"tool_name": "query_logs"},
                tool_name="query_logs",
                tool_outcome=None,
                step_key="debug_logs",
            ),
        ),
        now=now,
    )

    assert alert is not None
    assert alert["metadata"]["pending_event_id"] == "tool-request-1"


def test_has_drift_alert_detects_trace_drift_summary() -> None:
    summary = ArtanaRunTraceSummaryRecord(
        summary_type="trace::drift",
        timestamp=datetime.now(UTC),
        step_key="step-1",
        payload={"drift_fields": ["prompt"], "forked": True},
    )

    assert _has_drift_alert(
        trace=_build_trace_record(summaries=(summary,)),
        fallback_snapshot=None,
    )


def test_resolve_budget_warning_detects_high_cost_ratio() -> None:
    summary = ArtanaRunTraceSummaryRecord(
        summary_type="trace::cost",
        timestamp=datetime.now(UTC),
        step_key="cost",
        payload={"total_cost": 0.81, "budget_usd_limit": 1.0},
    )

    alert = _resolve_budget_warning(trace=_build_trace_record(summaries=(summary,)))

    assert alert is not None
    assert alert["metadata"]["budget_ratio"] == 0.81


def test_build_alerts_includes_failed_stuck_unknown_drift_and_budget() -> None:
    now = datetime.now(UTC)
    summaries = (
        ArtanaRunTraceSummaryRecord(
            summary_type="trace::drift",
            timestamp=now - timedelta(minutes=9),
            step_key="step-1",
            payload={"drift_fields": ["context"], "forked": False},
        ),
        ArtanaRunTraceSummaryRecord(
            summary_type="trace::cost",
            timestamp=now - timedelta(minutes=9),
            step_key="cost",
            payload={"total_cost": 0.9, "budget_usd_limit": 1.0},
        ),
    )
    events = (
        ArtanaRunTraceEventRecord(
            seq=1,
            event_id="model-req-1",
            event_type="model_requested",
            timestamp=now - timedelta(minutes=7),
            parent_step_key=None,
            payload={"model": "gpt-5"},
            tool_name=None,
            tool_outcome=None,
            step_key="generate",
        ),
    )
    service = ArtanaObservabilityService(session=None)
    alerts = service._build_alerts(
        trace=_build_trace_record(
            status="failed",
            updated_at=now - timedelta(minutes=11),
            events=events,
            summaries=summaries,
            failure_reason="model timeout",
        ),
        fallback_snapshot=None,
        now=now,
    )

    alert_codes = {str(alert["code"]) for alert in alerts}
    assert alert_codes == {
        "failed_run",
        "tool_unknown_outcome",
        "drift_detected",
        "budget_warning",
    }


def test_load_linked_records_resolves_documents_extractions_and_provenance(
    db_session,
) -> None:
    user = UserModel(
        email=f"artana-link-{uuid4().hex}@example.com",
        username=f"artana-link-{uuid4().hex[:10]}",
        full_name="Artana Link Tester",
        hashed_password="hashed_password",
        role="admin",
        status="active",
    )
    db_session.add(user)
    db_session.flush()

    space = ResearchSpaceModel(
        slug=f"artana-link-space-{uuid4().hex[:12]}",
        name="Artana Link Space",
        description="Test space",
        owner_id=user.id,
        status="active",
    )
    db_session.add(space)
    db_session.flush()

    source = UserDataSourceModel(
        id=str(uuid4()),
        owner_id=str(user.id),
        research_space_id=str(space.id),
        name="Artana Link Source",
        description="PubMed source",
        source_type=SourceTypeEnum.PUBMED,
        configuration={"query": "MED13"},
        status=SourceStatusEnum.ACTIVE,
        ingestion_schedule={"enabled": False},
        quality_metrics={},
        tags=[],
        version="1.0",
    )
    db_session.add(source)
    db_session.flush()

    job = IngestionJobModel(
        id=str(uuid4()),
        source_id=str(source.id),
        job_kind=IngestionJobKindEnum.PIPELINE_ORCHESTRATION,
        trigger=IngestionTriggerEnum.MANUAL,
        triggered_by=str(user.id),
        triggered_at=_iso_timestamp(),
        status=IngestionStatusEnum.COMPLETED,
        started_at=_iso_timestamp(),
        completed_at=_iso_timestamp(),
        metrics={},
        errors=[],
        provenance={},
        job_metadata={},
        source_config_snapshot={},
        dictionary_version_used=1,
        replay_policy="strict",
    )
    db_session.add(job)
    db_session.flush()

    queue_item = ExtractionQueueItemModel(
        id=str(uuid4()),
        publication_id=None,
        pubmed_id="40214304",
        source_type=SourceTypeEnum.PUBMED.value,
        source_record_id="PMID-40214304",
        raw_storage_key=None,
        payload_ref=None,
        source_id=str(source.id),
        ingestion_job_id=str(job.id),
        status=ExtractionStatusEnum.COMPLETED,
        attempts=1,
        last_error=None,
        extraction_version=1,
        metadata_payload={"pipeline_run_id": "pipeline-1"},
    )
    db_session.add(queue_item)
    db_session.flush()

    run_id = "extract:pubmed:test-run"
    document = SourceDocumentModel(
        id=str(uuid4()),
        research_space_id=str(space.id),
        source_id=str(source.id),
        ingestion_job_id=str(job.id),
        external_record_id="PMID-40214304",
        source_type=SourceTypeEnum.PUBMED.value,
        document_format="json",
        extraction_status="extracted",
        extraction_agent_run_id=run_id,
        metadata_payload={"pipeline_run_id": "pipeline-1"},
    )
    extraction = PublicationExtractionModel(
        id=str(uuid4()),
        publication_id=None,
        pubmed_id="40214304",
        source_id=str(source.id),
        ingestion_job_id=str(job.id),
        queue_item_id=str(queue_item.id),
        status=ExtractionOutcomeEnum.COMPLETED,
        extraction_version=1,
        processor_name="artana",
        processor_version="1.0",
        text_source="abstract",
        document_reference=None,
        facts=[],
        metadata_payload={"pipeline_run_id": "pipeline-1", "agent_run_id": run_id},
    )
    provenance = ProvenanceModel(
        research_space_id=space.id,
        source_type="AI_EXTRACTION",
        source_ref="test://pubmed/40214304",
        extraction_run_id=run_id,
        mapping_method="llm",
        mapping_confidence=0.92,
        agent_model="gpt-5",
        raw_input={"pmid": "40214304"},
    )
    db_session.add_all([document, extraction, provenance])
    db_session.commit()

    service = ArtanaObservabilityService(session=db_session)
    linked_records = service._load_linked_records(
        run_id=run_id,
        research_space_id=str(space.id),
    )

    record_types = {str(record["record_type"]) for record in linked_records}
    assert record_types == {
        "source_document",
        "publication_extraction",
        "provenance",
    }


def test_list_admin_runs_filters_by_alert_code_and_paginates() -> None:
    now = datetime.now(UTC)
    service = ArtanaObservabilityService(session=None)

    snapshots = [
        _RunSnapshotRow(
            run_id="run-failed",
            tenant_id="space-1",
            last_event_seq=2,
            last_event_type="run_failed",
            updated_at=now - timedelta(minutes=20),
            status="failed",
            blocked_on=None,
            failure_reason="timeout",
            error_category=None,
            diagnostics_json=None,
            last_step_key="step-1",
            drift_count=0,
            last_stage="extract",
            last_tool=None,
            model_cost_total=0.0,
            open_pause_count=0,
            explain_status="failed",
            explain_failure_reason="timeout",
            explain_failure_step="step-1",
        ),
        _RunSnapshotRow(
            run_id="run-drift",
            tenant_id="space-1",
            last_event_seq=3,
            last_event_type="run_summary",
            updated_at=now - timedelta(minutes=2),
            status="running",
            blocked_on=None,
            failure_reason=None,
            error_category=None,
            diagnostics_json=None,
            last_step_key="step-2",
            drift_count=2,
            last_stage="graph",
            last_tool=None,
            model_cost_total=0.0,
            open_pause_count=0,
            explain_status="completed",
            explain_failure_reason=None,
            explain_failure_step=None,
        ),
    ]

    service._list_snapshot_rows = lambda **_: snapshots  # type: ignore[method-assign]
    service._load_linked_records = lambda **_: [  # type: ignore[method-assign]
        {
            "record_type": "source_document",
            "record_id": "doc-1",
            "source_id": "source-1",
            "source_type": "pubmed",
        },
    ]

    payload = service.list_admin_runs(
        q=None,
        status=None,
        space_id=None,
        source_type="pubmed",
        alert_code="drift_detected",
        since_hours=None,
        page=1,
        per_page=1,
    )

    assert payload["total"] == 1
    assert payload["runs"][0]["run_id"] == "run-drift"
