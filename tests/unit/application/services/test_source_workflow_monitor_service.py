"""Unit tests for SourceWorkflowMonitorService Artana progress shaping."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, cast
from unittest.mock import Mock
from uuid import UUID, uuid4

from src.application.services._source_workflow_monitor_shared import PipelineRunRecord
from src.application.services.ports.run_progress_port import (
    RunProgressSnapshot,
)
from src.application.services.source_workflow_monitor_service import (
    SourceWorkflowMonitorService,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from src.models.database.user_data_source import UserDataSourceModel
    from src.type_definitions.common import JSONObject


class _StubRunProgressPort:
    def __init__(self, snapshots: dict[str, RunProgressSnapshot]) -> None:
        self._snapshots = snapshots

    def get_run_progress(self, *, run_id: str) -> RunProgressSnapshot | None:
        return self._snapshots.get(run_id)


def _snapshot(run_id: str, status: str, percent: int) -> RunProgressSnapshot:
    now = datetime.now(UTC)
    return RunProgressSnapshot(
        run_id=run_id,
        status=status,
        percent=percent,
        current_stage="stage_a",
        completed_stages=("setup",),
        started_at=now,
        updated_at=now,
        eta_seconds=42,
    )


@dataclass(frozen=True)
class _QueueStatus:
    value: str


@dataclass(frozen=True)
class _QueueRow:
    id: str
    source_record_id: str
    pubmed_id: str | None
    status: _QueueStatus
    attempts: int
    last_error: str | None
    ingestion_job_id: str
    queued_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    metadata_payload: dict[str, object]


class _FakeScalarResult:
    def __init__(self, rows: list[_QueueRow]) -> None:
        self._rows = rows

    def all(self) -> list[_QueueRow]:
        return self._rows


class _FakeExecuteResult:
    def __init__(self, rows: list[_QueueRow]) -> None:
        self._rows = rows

    def scalars(self) -> _FakeScalarResult:
        return _FakeScalarResult(self._rows)


class _FakeSession:
    def __init__(self, rows: list[_QueueRow]) -> None:
        self._rows = rows

    def execute(self, _statement: object) -> _FakeExecuteResult:
        return _FakeExecuteResult(self._rows)


class _FakeDocumentOutcomeExecuteResult:
    def __init__(
        self,
        rows: list[tuple[str, str | None, dict[str, object]]],
    ) -> None:
        self._rows = rows

    def all(self) -> list[tuple[str, str | None, dict[str, object]]]:
        return self._rows


class _FakeDocumentOutcomeSession:
    def __init__(
        self,
        rows: list[tuple[str, str | None, dict[str, object]]],
    ) -> None:
        self._rows = rows

    def execute(self, _statement: object) -> _FakeDocumentOutcomeExecuteResult:
        return _FakeDocumentOutcomeExecuteResult(self._rows)


class _FakeRelationRowsExecuteResult:
    def __init__(self, rows: list[tuple[object, ...]]) -> None:
        self._rows = rows

    def all(self) -> list[tuple[object, ...]]:
        return self._rows


class _FakeRelationRowsSession:
    def __init__(self, rows: list[tuple[object, ...]]) -> None:
        self._rows = rows

    def execute(self, _statement: object) -> _FakeRelationRowsExecuteResult:
        return _FakeRelationRowsExecuteResult(self._rows)


class _PrefetchCaptureService(SourceWorkflowMonitorService):
    def __init__(self) -> None:
        super().__init__(session=Mock(), run_progress=None)
        self.captured_limits: dict[str, int] = {}
        self._record = PipelineRunRecord(
            payload={"run_id": "run-1"},
            run_id="run-1",
            job_id="job-1",
        )

    def _require_source(
        self,
        *,
        space_id: UUID,
        source_id: UUID,
    ) -> UserDataSourceModel:
        del space_id
        del source_id
        return cast("UserDataSourceModel", object())

    def _load_pipeline_runs(
        self,
        *,
        source_id: UUID,
        limit: int,
    ) -> list[PipelineRunRecord]:
        del source_id
        self.captured_limits["pipeline_runs"] = limit
        return [self._record]

    def _load_source_documents(
        self,
        *,
        source_id: UUID,
        run_id: str | None,
        ingestion_job_id: str | None,
        limit: int,
    ) -> list[JSONObject]:
        del source_id
        del run_id
        del ingestion_job_id
        self.captured_limits["documents"] = limit
        return []

    def _load_extraction_queue(
        self,
        *,
        source_id: UUID,
        run_id: str | None,
        ingestion_job_id: str | None,
        external_record_ids: set[str],
        limit: int,
    ) -> list[JSONObject]:
        del source_id
        del run_id
        del ingestion_job_id
        del external_record_ids
        self.captured_limits["queue"] = limit
        return []

    def _load_publication_extractions(
        self,
        *,
        source_id: UUID,
        run_id: str | None,
        ingestion_job_id: str | None,
        queue_item_ids: set[str],
        limit: int,
    ) -> list[JSONObject]:
        del source_id
        del run_id
        del ingestion_job_id
        del queue_item_ids
        self.captured_limits["extractions"] = limit
        return []


class _RunScopedFilterCaptureService(SourceWorkflowMonitorService):
    def __init__(self) -> None:
        super().__init__(session=Mock(), run_progress=None)
        self.captured: dict[str, tuple[str | None, str | None]] = {}
        self._record = PipelineRunRecord(
            payload={
                "run_id": "run-match",
                "status": "completed",
                "stage_statuses": {},
                "stage_errors": {},
                "stage_checkpoints": {},
                "stage_counters": {},
            },
            run_id="run-match",
            job_id="pipeline-job-id",
        )

    def _require_source(
        self,
        *,
        space_id: UUID,
        source_id: UUID,
    ) -> UserDataSourceModel:
        del space_id
        del source_id
        return cast("UserDataSourceModel", object())

    def _build_source_snapshot(self, source: UserDataSourceModel) -> JSONObject:
        del source
        return {"source_id": "source-1"}

    def _load_pipeline_runs(
        self,
        *,
        source_id: UUID,
        limit: int,
    ) -> list[PipelineRunRecord]:
        del source_id
        del limit
        return [self._record]

    def _load_source_documents(
        self,
        *,
        source_id: UUID,
        run_id: str | None,
        ingestion_job_id: str | None,
        limit: int,
    ) -> list[JSONObject]:
        del source_id
        del limit
        self.captured["documents"] = (run_id, ingestion_job_id)
        return []

    def _load_extraction_queue(
        self,
        *,
        source_id: UUID,
        run_id: str | None,
        ingestion_job_id: str | None,
        external_record_ids: set[str],
        limit: int,
    ) -> list[JSONObject]:
        del source_id
        del external_record_ids
        del limit
        self.captured["queue"] = (run_id, ingestion_job_id)
        return []

    def _load_publication_extractions(
        self,
        *,
        source_id: UUID,
        run_id: str | None,
        ingestion_job_id: str | None,
        queue_item_ids: set[str],
        limit: int,
    ) -> list[JSONObject]:
        del source_id
        del queue_item_ids
        del limit
        self.captured["extractions"] = (run_id, ingestion_job_id)
        return []

    def _build_relation_review_payload(  # noqa: PLR0913
        self,
        *,
        space_id: UUID,
        document_ids: set[str],
        document_context_by_id: dict[str, JSONObject],
        queue_id_to_document_id: dict[str, str],
        extraction_rows: list[JSONObject],
        limit: int,
    ) -> JSONObject:
        del space_id
        del document_ids
        del document_context_by_id
        del queue_id_to_document_id
        del extraction_rows
        del limit
        return {
            "persisted_relation_rows": [],
            "pending_review_relation_rows": [],
            "pending_review_relation_count": 0,
            "review_queue_rows": [],
            "rejected_relation_rows": [],
            "rejected_reason_counts": {},
        }

    def _build_operational_counters(  # noqa: PLR0913
        self,
        *,
        space_id: UUID,
        source_id: UUID,
        selected_run: PipelineRunRecord | None,
        graph_summary: JSONObject | None,
        relation_edge_delta: int,
        selected_run_id: str | None,
        selected_ingestion_job_id: str | None,
    ) -> JSONObject:
        del space_id
        del source_id
        del selected_run
        del graph_summary
        del relation_edge_delta
        del selected_run_id
        del selected_ingestion_job_id
        return {"last_pipeline_status": "completed"}

    def _build_artana_progress(
        self,
        *,
        selected_run_id: str | None,
        selected_run_payload: JSONObject | None,
        documents: list[JSONObject],
        extraction_rows: list[JSONObject],
        relation_rows: list[JSONObject],
    ) -> JSONObject:
        del selected_run_id
        del selected_run_payload
        del documents
        del extraction_rows
        del relation_rows
        return {}

    def _build_warnings(self, *, extraction_rows: list[JSONObject]) -> list[str]:
        del extraction_rows
        return []


def test_build_artana_progress_resolves_stage_snapshots_from_candidates() -> None:
    service = SourceWorkflowMonitorService(
        session=Mock(),
        run_progress=_StubRunProgressPort(
            {
                "pipeline:run:1": _snapshot("pipeline:run:1", "running", 10),
                "enrich:run:1": _snapshot("enrich:run:1", "completed", 100),
                "extract:run:1": _snapshot("extract:run:1", "running", 56),
                "graph:run:1": _snapshot("graph:run:1", "completed", 100),
            },
        ),
    )

    payload = service._build_artana_progress(
        selected_run_id="pipeline:run:1",
        selected_run_payload=None,
        documents=[
            {
                "metadata": {"content_enrichment_agent_run_id": "enrich:run:1"},
                "enrichment_agent_run_id": None,
                "extraction_agent_run_id": "extract:run:1",
            },
        ],
        extraction_rows=[
            {"metadata": {"extraction_run_id": "extract:run:1"}},
        ],
        relation_rows=[
            {"agent_run_id": "graph:run:1"},
        ],
    )

    assert payload["pipeline"]["status"] == "running"
    assert payload["pipeline"]["percent"] == 10
    assert payload["enrichment"]["run_id"] == "enrich:run:1"
    assert payload["extraction"]["run_id"] == "extract:run:1"
    assert payload["graph"]["run_id"] == "graph:run:1"


def test_build_artana_progress_returns_empty_stage_payload_when_unavailable() -> None:
    service = SourceWorkflowMonitorService(session=Mock(), run_progress=None)

    payload = service._build_artana_progress(
        selected_run_id="pipeline:missing",
        selected_run_payload=None,
        documents=[
            {
                "metadata": {"content_enrichment_agent_run_id": "enrich:missing"},
                "enrichment_agent_run_id": None,
                "extraction_agent_run_id": None,
            },
        ],
        extraction_rows=[],
        relation_rows=[],
    )

    assert payload["pipeline"]["run_id"] == "pipeline:missing"
    assert payload["pipeline"]["status"] is None
    assert payload["enrichment"]["run_id"] == "enrich:missing"
    assert payload["enrichment"]["status"] is None
    assert payload["extraction"]["run_id"] is None
    assert payload["graph"]["run_id"] is None


def test_build_artana_progress_falls_back_to_selected_pipeline_run_status() -> None:
    service = SourceWorkflowMonitorService(
        session=Mock(),
        run_progress=_StubRunProgressPort({}),
    )

    payload = service._build_artana_progress(
        selected_run_id="5caf33eb-1908-4c8c-b5c3-947a14708587",
        selected_run_payload={
            "run_id": "5caf33eb-1908-4c8c-b5c3-947a14708587",
            "status": "running",
            "started_at": "2026-02-27T00:16:32+00:00",
            "stage_statuses": {
                "ingestion": "completed",
                "enrichment": "running",
                "extraction": "pending",
                "graph": "pending",
            },
        },
        documents=[],
        extraction_rows=[],
        relation_rows=[],
    )

    assert payload["pipeline"]["run_id"] == "5caf33eb-1908-4c8c-b5c3-947a14708587"
    assert payload["pipeline"]["status"] == "running"
    assert payload["pipeline"]["percent"] == 25
    assert payload["pipeline"]["current_stage"] == "enrichment"
    assert payload["pipeline"]["completed_stages"] == ["ingestion"]


def test_build_artana_progress_ignores_non_graph_run_ids_for_graph_stage() -> None:
    service = SourceWorkflowMonitorService(
        session=Mock(),
        run_progress=_StubRunProgressPort(
            {
                "extract:run:1": _snapshot("extract:run:1", "running", 40),
            },
        ),
    )

    payload = service._build_artana_progress(
        selected_run_id="pipeline:run:1",
        selected_run_payload=None,
        documents=[
            {
                "metadata": {},
                "enrichment_agent_run_id": None,
                "extraction_agent_run_id": "extract:run:1",
            },
        ],
        extraction_rows=[],
        relation_rows=[
            {"agent_run_id": "extract:run:1"},
        ],
    )

    assert payload["extraction"]["run_id"] == "extract:run:1"
    assert payload["graph"]["run_id"] is None
    assert payload["graph"]["candidate_run_ids"] == []


def test_load_extraction_queue_filters_rows_to_selected_ingestion_job() -> None:
    now = datetime.now(UTC)
    service = SourceWorkflowMonitorService(
        session=cast(
            "Session",
            _FakeSession(
                [
                    _QueueRow(
                        id="queue-match",
                        source_record_id="PMID-123",
                        pubmed_id="123",
                        status=_QueueStatus("pending"),
                        attempts=1,
                        last_error=None,
                        ingestion_job_id="job-match",
                        queued_at=now,
                        started_at=None,
                        completed_at=None,
                        metadata_payload={"pipeline_run_id": "run-match"},
                    ),
                    _QueueRow(
                        id="queue-other-job",
                        source_record_id="PMID-123",
                        pubmed_id="123",
                        status=_QueueStatus("pending"),
                        attempts=1,
                        last_error=None,
                        ingestion_job_id="job-other",
                        queued_at=now,
                        started_at=None,
                        completed_at=None,
                        metadata_payload={"pipeline_run_id": "run-other"},
                    ),
                ],
            ),
        ),
        run_progress=None,
    )

    queue_rows = service._load_extraction_queue(
        source_id=uuid4(),
        run_id="run-match",
        ingestion_job_id="job-match",
        external_record_ids={"PMID-123"},
        limit=50,
    )

    assert [row["id"] for row in queue_rows] == ["queue-match"]


def test_list_workflow_events_caps_prefetch_limits() -> None:
    service = _PrefetchCaptureService()

    payload = service.list_workflow_events(
        space_id=uuid4(),
        source_id=uuid4(),
        run_id=None,
        limit=1000,
        since=None,
    )

    expected_limit = service._EVENT_PREFETCH_HARD_CAP
    assert service.captured_limits["pipeline_runs"] == expected_limit
    assert service.captured_limits["documents"] == expected_limit
    assert service.captured_limits["queue"] == expected_limit
    assert service.captured_limits["extractions"] == expected_limit
    assert payload["events"] == []


def test_monitor_run_scope_ignores_pipeline_job_id_for_document_filters() -> None:
    service = _RunScopedFilterCaptureService()

    payload = service.get_source_workflow_monitor(
        space_id=uuid4(),
        source_id=uuid4(),
        run_id="run-match",
        limit=5,
        include_graph=False,
    )

    assert payload["last_run"] is not None
    assert service.captured["documents"] == ("run-match", None)
    assert service.captured["queue"] == ("run-match", None)
    assert service.captured["extractions"] == ("run-match", None)


def test_monitor_run_scope_prefers_underlying_ingestion_job_id_when_present() -> None:
    service = _RunScopedFilterCaptureService()
    service._record = PipelineRunRecord(
        payload={
            "run_id": "run-match",
            "status": "completed",
            "ingestion_job_id": "ingestion-job-123",
            "stage_statuses": {},
            "stage_errors": {},
            "stage_checkpoints": {},
            "stage_counters": {},
        },
        run_id="run-match",
        job_id="pipeline-job-id",
    )

    payload = service.get_source_workflow_monitor(
        space_id=uuid4(),
        source_id=uuid4(),
        run_id="run-match",
        limit=5,
        include_graph=False,
    )

    assert payload["last_run"] is not None
    assert service.captured["documents"] == ("run-match", "ingestion-job-123")
    assert service.captured["queue"] == ("run-match", "ingestion-job-123")
    assert service.captured["extractions"] == ("run-match", "ingestion-job-123")


def test_count_document_extraction_outcomes_reports_timeout_failures() -> None:
    service = SourceWorkflowMonitorService(
        session=cast(
            "Session",
            _FakeDocumentOutcomeSession(
                [
                    (
                        "failed",
                        "job-1",
                        {
                            "pipeline_run_id": "run-1",
                            "entity_recognition_failure_reason": (
                                "agent_execution_timeout"
                            ),
                        },
                    ),
                    (
                        "failed",
                        "job-1",
                        {
                            "pipeline_run_id": "run-1",
                            "entity_recognition_failure_reason": (
                                "dictionary_mutation_failed"
                            ),
                        },
                    ),
                    (
                        "failed",
                        "job-1",
                        {
                            "pipeline_run_id": "run-1",
                            "extraction_stage_error_code": "EXTRACTION_STAGE_TIMEOUT",
                        },
                    ),
                    (
                        "extracted",
                        "job-1",
                        {"pipeline_run_id": "run-1"},
                    ),
                    (
                        "skipped",
                        "job-1",
                        {"pipeline_run_id": "run-1"},
                    ),
                ],
            ),
        ),
        run_progress=None,
    )

    extracted, failed, skipped, timeout_failed = (
        service._count_document_extraction_outcomes(
            source_id=uuid4(),
            run_id="run-1",
            ingestion_job_id="job-1",
        )
    )

    assert extracted == 1
    assert failed == 3
    assert skipped == 1
    assert timeout_failed == 2


def test_resolve_paper_links_dedupes_and_orders_supported_identifiers() -> None:
    service = SourceWorkflowMonitorService(session=Mock(), run_progress=None)

    links = service._resolve_paper_links(
        source_type="pubmed",
        external_record_id="pmid:40214304",
        metadata={
            "doi": "10.1000/j.jmb.2026.01.001",
            "pmcid": "PMC12419501",
            "url": "https://pubmed.ncbi.nlm.nih.gov/40214304/",
        },
    )

    labels = [str(link.get("label")) for link in links]
    urls = [str(link.get("url")) for link in links]

    assert labels == ["PubMed", "PMC", "DOI"]
    assert urls == [
        "https://pubmed.ncbi.nlm.nih.gov/40214304/",
        "https://pmc.ncbi.nlm.nih.gov/articles/PMC12419501/",
        "https://doi.org/10.1000/j.jmb.2026.01.001",
    ]


def test_load_document_relations_includes_sentence_provenance_and_paper_links() -> None:
    document_uuid = uuid4()
    relation_uuid = uuid4()
    source_uuid = uuid4()
    target_uuid = uuid4()
    evidence_uuid = uuid4()

    service = SourceWorkflowMonitorService(
        session=cast(
            "Session",
            _FakeRelationRowsSession(
                [
                    (
                        document_uuid,
                        relation_uuid,
                        "ASSOCIATED_WITH",
                        "DRAFT",
                        0.73,
                        source_uuid,
                        target_uuid,
                        evidence_uuid,
                        0.73,
                        "Optional relation summary.",
                        "Generated reviewer-aid sentence.",
                        "artana_generated",
                        "low",
                        "No direct span found; inferred from extraction context.",
                        "run:test",
                        "MED13",
                        "Cardiomyopathy",
                    ),
                ],
            ),
        ),
        run_progress=None,
    )

    rows = service._load_document_relations(
        space_id=uuid4(),
        document_ids={str(document_uuid)},
        document_context_by_id={
            str(document_uuid): {
                "external_record_id": "pmid:40214304",
                "source_type": "pubmed",
                "metadata": {},
            },
        },
        limit=20,
    )

    assert len(rows) == 1
    row = rows[0]
    assert row["evidence_sentence_source"] == "artana_generated"
    assert row["evidence_sentence_confidence"] == "low"
    assert (
        row["evidence_sentence_rationale"]
        == "No direct span found; inferred from extraction context."
    )
    links = row["paper_links"]
    assert isinstance(links, list)
    assert len(links) == 1
    first_link = links[0]
    assert first_link["label"] == "PubMed"
    assert first_link["url"] == "https://pubmed.ncbi.nlm.nih.gov/40214304/"
