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
