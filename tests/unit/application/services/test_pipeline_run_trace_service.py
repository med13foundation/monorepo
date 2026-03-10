"""Unit tests for PipelineRunTraceService safeguards."""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import TYPE_CHECKING
from unittest.mock import Mock, patch
from uuid import UUID, uuid4

from src.application.services._artana_observability_models import _RunSnapshotRow
from src.application.services.pipeline_run_trace_service import (
    PipelineRunTraceService,
)
from src.domain.repositories.pipeline_run_event_repository import (
    PipelineRunEventRepository,
)

if TYPE_CHECKING:
    from src.domain.entities.pipeline_run_event import PipelineRunEvent


class _StubPipelineRunEventRepository(PipelineRunEventRepository):
    def __init__(self) -> None:
        self.events: list[PipelineRunEvent] = []

    def append(self, event: PipelineRunEvent) -> PipelineRunEvent:
        persisted = event.model_copy(update={"seq": len(self.events) + 1})
        self.events.append(persisted)
        return persisted

    def list_events(  # noqa: PLR0913
        self,
        *,
        research_space_id: UUID | None = None,
        source_id: UUID | None = None,
        pipeline_run_id: str | None = None,
        stage: str | None = None,
        level: str | None = None,
        scope_kind: str | None = None,
        scope_id: str | None = None,
        agent_kind: str | None = None,
        limit: int = 200,
    ) -> list[PipelineRunEvent]:
        del research_space_id
        del source_id
        del pipeline_run_id
        del stage
        del level
        del scope_kind
        del scope_id
        del agent_kind
        del limit
        return list(self.events)


def test_record_event_truncates_long_scope_ids_and_preserves_full_value() -> None:
    repository = _StubPipelineRunEventRepository()
    service = PipelineRunTraceService(
        session=Mock(),
        event_repository=repository,
    )
    long_scope_id = "query:" + ("MED13-" * 80)

    event = service.record_event(
        research_space_id=uuid4(),
        source_id=uuid4(),
        pipeline_run_id="run-1",
        event_type="query_resolved",
        scope_kind="query",
        scope_id=long_scope_id,
        message="Resolved query.",
        payload={"executed_query": long_scope_id},
    )

    assert event.scope_id is not None
    assert len(event.scope_id) <= 255
    assert "...#" in event.scope_id
    assert event.payload["scope_id_full"] == long_scope_id


class _FakeScalarResult:
    def __init__(self, rows: list[object]) -> None:
        self._rows = rows

    def all(self) -> list[object]:
        return self._rows


class _FakeExecuteResult:
    def __init__(self, rows: list[object]) -> None:
        self._rows = rows

    def scalars(self) -> _FakeScalarResult:
        return _FakeScalarResult(self._rows)


class _FakeSession:
    def __init__(self, rows: list[object]) -> None:
        self._rows = rows

    def execute(self, _statement: object) -> _FakeExecuteResult:
        return _FakeExecuteResult(self._rows)


def test_load_job_run_ids_reads_query_progress_run_id() -> None:
    repository = _StubPipelineRunEventRepository()
    service = PipelineRunTraceService(
        session=_FakeSession(
            [
                SimpleNamespace(
                    job_metadata={
                        "pipeline_run": {
                            "run_id": "pipeline-run-1",
                            "query_progress": {
                                "query_generation_run_id": "query-run-123",
                            },
                        },
                    },
                ),
            ],
        ),
        event_repository=repository,
    )
    stage_run_ids: dict[str, list[str]] = defaultdict(list)

    service._load_job_run_ids(
        research_space_id=str(uuid4()),
        pipeline_run_id="pipeline-run-1",
        stage_run_ids=stage_run_ids,
    )

    assert stage_run_ids["query_generation"] == ["query-run-123"]


def test_resolve_cost_summary_overrides_snapshot_stage_costs_with_direct_costs() -> (
    None
):
    repository = _StubPipelineRunEventRepository()
    service = PipelineRunTraceService(
        session=Mock(),
        event_repository=repository,
    )
    service._load_stage_run_ids = Mock(  # type: ignore[method-assign]
        return_value={"query_generation": ["query-run-123"]},
    )
    service._load_kernel_event_costs_by_run_id = Mock(  # type: ignore[method-assign]
        return_value={},
    )

    with patch(
        "src.application.services.pipeline_run_trace_service.list_snapshot_rows",
        return_value=[
            _RunSnapshotRow(
                run_id="query-run-123",
                tenant_id=str(uuid4()),
                last_event_seq=1,
                last_event_type="model.completed",
                updated_at=datetime.now(UTC),
                status="completed",
                blocked_on=None,
                failure_reason=None,
                error_category=None,
                diagnostics_json=None,
                last_step_key="query.generate.pubmed.v1",
                drift_count=0,
                last_stage="query_generation",
                last_tool=None,
                model_cost_total=0.5,
                open_pause_count=0,
                explain_status=None,
                explain_failure_reason=None,
                explain_failure_step=None,
            ),
        ],
    ):
        summary = service.resolve_cost_summary(
            research_space_id=uuid4(),
            pipeline_run_id="pipeline-run-1",
            additional_stage_costs_usd={
                "query_generation": 0.2,
                "ingestion": 0.05,
            },
        )

    assert summary.stage_costs_usd["query_generation"] == 0.2
    assert summary.stage_costs_usd["ingestion"] == 0.05
    assert summary.total_cost_usd == 0.25


def test_resolve_cost_summary_loads_query_generation_cost_across_tenants() -> None:
    repository = _StubPipelineRunEventRepository()
    service = PipelineRunTraceService(
        session=Mock(),
        event_repository=repository,
    )
    service._load_stage_run_ids = Mock(  # type: ignore[method-assign]
        return_value={
            "query_generation": ["query-run-123"],
            "extraction": ["extract-run-123"],
        },
    )
    service._load_kernel_event_costs_by_run_id = Mock(  # type: ignore[method-assign]
        return_value={},
    )

    def _snapshot_rows(
        _session: object,
        *,
        run_id: str | None,
        tenant_id: str | None,
        status: str | None,
        updated_since: datetime | None,
    ) -> list[_RunSnapshotRow]:
        del _session
        del status
        del updated_since
        assert tenant_id is None
        if run_id == "query-run-123":
            return [
                _RunSnapshotRow(
                    run_id="query-run-123",
                    tenant_id="med13_query_agent",
                    last_event_seq=1,
                    last_event_type="model.completed",
                    updated_at=datetime.now(UTC),
                    status="completed",
                    blocked_on=None,
                    failure_reason=None,
                    error_category=None,
                    diagnostics_json=None,
                    last_step_key="query.generate.pubmed.v1",
                    drift_count=0,
                    last_stage="query_generation",
                    last_tool=None,
                    model_cost_total=0.004838,
                    open_pause_count=0,
                    explain_status=None,
                    explain_failure_reason=None,
                    explain_failure_step=None,
                ),
            ]
        if run_id == "extract-run-123":
            return [
                _RunSnapshotRow(
                    run_id="extract-run-123",
                    tenant_id=str(uuid4()),
                    last_event_seq=2,
                    last_event_type="model.completed",
                    updated_at=datetime.now(UTC),
                    status="completed",
                    blocked_on=None,
                    failure_reason=None,
                    error_category=None,
                    diagnostics_json=None,
                    last_step_key="extract.pubmed.v1",
                    drift_count=0,
                    last_stage="extraction",
                    last_tool=None,
                    model_cost_total=0.125,
                    open_pause_count=0,
                    explain_status=None,
                    explain_failure_reason=None,
                    explain_failure_step=None,
                ),
            ]
        return []

    with patch(
        "src.application.services.pipeline_run_trace_service.list_snapshot_rows",
        side_effect=_snapshot_rows,
    ):
        summary = service.resolve_cost_summary(
            research_space_id=uuid4(),
            pipeline_run_id="pipeline-run-1",
        )

    assert summary.stage_costs_usd["query_generation"] == 0.004838
    assert summary.stage_costs_usd["extraction"] == 0.125
    assert summary.total_cost_usd == 0.129838


def test_resolve_cost_summary_falls_back_to_kernel_event_costs_when_snapshot_is_zero() -> (
    None
):
    repository = _StubPipelineRunEventRepository()
    service = PipelineRunTraceService(
        session=Mock(),
        event_repository=repository,
    )
    service._load_stage_run_ids = Mock(  # type: ignore[method-assign]
        return_value={"query_generation": ["query-run-123"]},
    )
    service._load_kernel_event_costs_by_run_id = Mock(  # type: ignore[method-assign]
        return_value={"query-run-123": 0.004838},
    )

    with patch(
        "src.application.services.pipeline_run_trace_service.list_snapshot_rows",
        return_value=[
            _RunSnapshotRow(
                run_id="query-run-123",
                tenant_id="med13_query_agent",
                last_event_seq=3,
                last_event_type="model_terminal",
                updated_at=datetime.now(UTC),
                status="failed",
                blocked_on=None,
                failure_reason="timeout",
                error_category="internal",
                diagnostics_json=None,
                last_step_key="query.generate.pubmed.v1",
                drift_count=0,
                last_stage=None,
                last_tool=None,
                model_cost_total=0.0,
                open_pause_count=0,
                explain_status=None,
                explain_failure_reason=None,
                explain_failure_step=None,
            ),
        ],
    ):
        summary = service.resolve_cost_summary(
            research_space_id=uuid4(),
            pipeline_run_id="pipeline-run-1",
        )

    assert summary.stage_costs_usd["query_generation"] == 0.004838
    assert summary.total_cost_usd == 0.004838
