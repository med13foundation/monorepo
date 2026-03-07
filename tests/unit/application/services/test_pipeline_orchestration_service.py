"""Tests for PipelineOrchestrationService run checkpoint persistence."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, NoReturn
from uuid import UUID, uuid4

import pytest

from src.application.services.pipeline_orchestration_service import (
    ActivePipelineRunExistsError,
    PipelineOrchestrationDependencies,
    PipelineOrchestrationService,
    PipelineQueueFullError,
)
from src.domain.entities.ingestion_job import (
    IngestionError,
    IngestionJob,
    IngestionJobKind,
    IngestionStatus,
    IngestionTrigger,
    JobMetrics,
)
from src.domain.repositories.ingestion_job_repository import IngestionJobRepository
from src.type_definitions.json_utils import to_json_value

if TYPE_CHECKING:
    from src.type_definitions.common import JSONObject


def _unsupported(method_name: str) -> NoReturn:
    raise NotImplementedError(f"{method_name} is not implemented in test stub")


@dataclass(frozen=True)
class StubIngestionSummary:
    source_id: UUID
    fetched_records: int = 4
    parsed_publications: int = 4
    created_publications: int = 2
    updated_publications: int = 1
    extraction_targets: tuple[object, ...] = ()
    executed_query: str | None = "med13"
    query_signature: str | None = None
    checkpoint_before: JSONObject | None = None
    checkpoint_after: JSONObject | None = None
    checkpoint_kind: str | None = None
    query_generation_execution_mode: str | None = "ai"
    query_generation_fallback_reason: str | None = None
    new_records: int = 0
    updated_records: int = 0
    unchanged_records: int = 0
    skipped_records: int = 0
    ingestion_job_id: UUID | None = None


@dataclass(frozen=True)
class StubEnrichmentSummary:
    processed: int = 3
    enriched: int = 3
    failed: int = 0
    ai_runs: int = 1
    deterministic_runs: int = 0
    errors: tuple[str, ...] = ()


@dataclass(frozen=True)
class StubExtractionSummary:
    processed: int = 3
    extracted: int = 3
    failed: int = 0
    persisted_relations_count: int = 0
    concept_members_created_count: int = 0
    concept_aliases_created_count: int = 0
    concept_decisions_proposed_count: int = 0
    derived_graph_seed_entity_ids: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()


@dataclass(frozen=True)
class StubGraphOutcome:
    persisted_relations_count: int = 1
    errors: tuple[str, ...] = ()


@dataclass(frozen=True)
class StubGraphSearchResultEntry:
    entity_id: str


@dataclass(frozen=True)
class StubGraphSearchContract:
    results: tuple[StubGraphSearchResultEntry, ...] = ()


class StubIngestionSchedulingService:
    def __init__(
        self,
        summary: StubIngestionSummary,
        *,
        error: Exception | None = None,
    ) -> None:
        self._summary = summary
        self._error = error
        self.calls: list[UUID] = []

    async def trigger_ingestion(self, source_id: UUID) -> StubIngestionSummary:
        self.calls.append(source_id)
        if self._error is not None:
            raise self._error
        return self._summary


class StubContentEnrichmentService:
    def __init__(
        self,
        summary: StubEnrichmentSummary,
        *,
        error: Exception | None = None,
    ) -> None:
        self._summary = summary
        self._error = error
        self.calls: list[dict[str, object]] = []

    async def process_pending_documents(  # noqa: PLR0913
        self,
        *,
        limit: int = 25,
        source_id: UUID | None = None,
        research_space_id: UUID | None = None,
        source_type: str | None = None,
        model_id: str | None = None,
        pipeline_run_id: str | None = None,
    ) -> StubEnrichmentSummary:
        self.calls.append(
            {
                "limit": limit,
                "source_id": source_id,
                "research_space_id": research_space_id,
                "source_type": source_type,
                "model_id": model_id,
                "pipeline_run_id": pipeline_run_id,
            },
        )
        if self._error is not None:
            raise self._error
        return self._summary


class StubEntityRecognitionService:
    def __init__(
        self,
        summary: StubExtractionSummary,
        *,
        error: Exception | None = None,
    ) -> None:
        self._summary = summary
        self._error = error
        self.calls: list[dict[str, object]] = []

    async def process_pending_documents(  # noqa: PLR0913
        self,
        *,
        limit: int = 25,
        source_id: UUID | None = None,
        research_space_id: UUID | None = None,
        source_type: str | None = None,
        model_id: str | None = None,
        shadow_mode: bool | None = None,
        pipeline_run_id: str | None = None,
    ) -> StubExtractionSummary:
        self.calls.append(
            {
                "limit": limit,
                "source_id": source_id,
                "research_space_id": research_space_id,
                "source_type": source_type,
                "model_id": model_id,
                "shadow_mode": shadow_mode,
                "pipeline_run_id": pipeline_run_id,
            },
        )
        if self._error is not None:
            raise self._error
        return self._summary


class SlowEntityRecognitionService(StubEntityRecognitionService):
    def __init__(
        self,
        summary: StubExtractionSummary,
        *,
        delay_seconds: float,
    ) -> None:
        super().__init__(summary)
        self._delay_seconds = delay_seconds

    async def process_pending_documents(  # noqa: PLR0913
        self,
        *,
        limit: int = 25,
        source_id: UUID | None = None,
        research_space_id: UUID | None = None,
        source_type: str | None = None,
        model_id: str | None = None,
        shadow_mode: bool | None = None,
        pipeline_run_id: str | None = None,
    ) -> StubExtractionSummary:
        self.calls.append(
            {
                "limit": limit,
                "source_id": source_id,
                "research_space_id": research_space_id,
                "source_type": source_type,
                "model_id": model_id,
                "shadow_mode": shadow_mode,
                "pipeline_run_id": pipeline_run_id,
            },
        )
        await asyncio.sleep(self._delay_seconds)
        return self._summary


class StubGraphConnectionService:
    def __init__(self, outcome: StubGraphOutcome) -> None:
        self._outcome = outcome
        self.calls: list[dict[str, object]] = []

    async def discover_connections_for_seed(  # noqa: PLR0913
        self,
        *,
        research_space_id: str,
        seed_entity_id: str,
        source_type: str,
        model_id: str | None = None,
        relation_types: list[str] | None = None,
        max_depth: int = 2,
        shadow_mode: bool | None = None,
        pipeline_run_id: str | None = None,
    ) -> StubGraphOutcome:
        self.calls.append(
            {
                "research_space_id": research_space_id,
                "seed_entity_id": seed_entity_id,
                "source_type": source_type,
                "model_id": model_id,
                "relation_types": relation_types,
                "max_depth": max_depth,
                "shadow_mode": shadow_mode,
                "pipeline_run_id": pipeline_run_id,
            },
        )
        return self._outcome


class StubGraphSearchService:
    def __init__(
        self,
        contract: StubGraphSearchContract,
        *,
        error: Exception | None = None,
    ) -> None:
        self._contract = contract
        self._error = error
        self.calls: list[dict[str, object]] = []

    async def search(  # noqa: PLR0913
        self,
        *,
        question: str,
        research_space_id: str,
        max_depth: int = 2,
        top_k: int = 25,
        include_evidence_chains: bool = True,
        force_agent: bool = False,
        model_id: str | None = None,
    ) -> StubGraphSearchContract:
        self.calls.append(
            {
                "question": question,
                "research_space_id": research_space_id,
                "max_depth": max_depth,
                "top_k": top_k,
                "include_evidence_chains": include_evidence_chains,
                "force_agent": force_agent,
                "model_id": model_id,
            },
        )
        if self._error is not None:
            raise self._error
        return self._contract


class StubPipelineRunRepository(IngestionJobRepository):
    def __init__(self) -> None:
        self.saved: list[IngestionJob] = []

    @staticmethod
    def _pipeline_payload(job: IngestionJob) -> JSONObject:
        return _coerce_json_object(job.metadata.get("pipeline_run"))

    @classmethod
    def _queue_status(cls, job: IngestionJob) -> str | None:
        raw_value = cls._pipeline_payload(job).get("queue_status")
        if isinstance(raw_value, str) and raw_value.strip():
            return raw_value.strip()
        return None

    @classmethod
    def _run_id(cls, job: IngestionJob) -> str | None:
        raw_value = cls._pipeline_payload(job).get("run_id")
        if isinstance(raw_value, str) and raw_value.strip():
            return raw_value.strip()
        return None

    @staticmethod
    def _update_pipeline_metadata(
        job: IngestionJob,
        **fields: object,
    ) -> JSONObject:
        metadata = _coerce_json_object(job.metadata)
        pipeline_payload = _coerce_json_object(metadata.get("pipeline_run"))
        for key, value in fields.items():
            pipeline_payload[str(key)] = to_json_value(value)
        metadata["pipeline_run"] = pipeline_payload
        return metadata

    def _latest_jobs(self) -> list[IngestionJob]:
        latest_by_id: dict[UUID, IngestionJob] = {}
        for job in self.saved:
            latest_by_id[job.id] = job
        return list(latest_by_id.values())

    def save(self, job: IngestionJob) -> IngestionJob:
        self.saved.append(job)
        return job

    def find_by_id(self, job_id: UUID) -> IngestionJob | None:
        for job in self._latest_jobs():
            if job.id == job_id:
                return job
        return None

    def find_by_source(
        self,
        source_id: UUID,
        skip: int = 0,
        limit: int = 50,
    ) -> list[IngestionJob]:
        matching = [job for job in self._latest_jobs() if job.source_id == source_id]
        matching.sort(key=lambda job: job.triggered_at, reverse=True)
        return matching[skip : skip + limit]

    def find_by_trigger(
        self,
        trigger: IngestionTrigger,
        skip: int = 0,
        limit: int = 50,
    ) -> list[IngestionJob]:
        _unsupported("find_by_trigger")

    def find_by_status(
        self,
        status: IngestionStatus,
        skip: int = 0,
        limit: int = 50,
    ) -> list[IngestionJob]:
        matching = [job for job in self._latest_jobs() if job.status == status]
        matching.sort(key=lambda job: job.triggered_at, reverse=True)
        return matching[skip : skip + limit]

    def find_running_jobs(self, skip: int = 0, limit: int = 50) -> list[IngestionJob]:
        return self.find_by_status(IngestionStatus.RUNNING, skip=skip, limit=limit)

    def find_failed_jobs(
        self,
        since: datetime | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> list[IngestionJob]:
        _ = since
        return self.find_by_status(IngestionStatus.FAILED, skip=skip, limit=limit)

    def find_recent_jobs(
        self,
        hours: int = 24,
        skip: int = 0,
        limit: int = 50,
    ) -> list[IngestionJob]:
        _unsupported("find_recent_jobs")

    def find_by_triggered_by(
        self,
        user_id: UUID,
        skip: int = 0,
        limit: int = 50,
    ) -> list[IngestionJob]:
        _unsupported("find_by_triggered_by")

    def update_status(
        self,
        job_id: UUID,
        status: IngestionStatus,
    ) -> IngestionJob | None:
        _unsupported("update_status")

    def update_metrics(
        self,
        job_id: UUID,
        metrics: JobMetrics,
    ) -> IngestionJob | None:
        _unsupported("update_metrics")

    def add_error(self, job_id: UUID, error: IngestionError) -> IngestionJob | None:
        _unsupported("add_error")

    def start_job(self, job_id: UUID) -> IngestionJob | None:
        _unsupported("start_job")

    def complete_job(self, job_id: UUID, metrics: JobMetrics) -> IngestionJob | None:
        _unsupported("complete_job")

    def fail_job(self, job_id: UUID, error: IngestionError) -> IngestionJob | None:
        _unsupported("fail_job")

    def delete_old_jobs(self, days: int = 90) -> int:
        _unsupported("delete_old_jobs")

    def count_by_source(self, source_id: UUID) -> int:
        return len(self.find_by_source(source_id))

    def count_by_status(self, status: IngestionStatus) -> int:
        return len(self.find_by_status(status))

    def count_by_trigger(self, trigger: IngestionTrigger) -> int:
        _unsupported("count_by_trigger")

    def exists(self, job_id: UUID) -> bool:
        return self.find_by_id(job_id) is not None

    def get_job_statistics(self, source_id: UUID | None = None) -> JSONObject:
        _ = source_id
        return {}

    def get_recent_failures(
        self,
        limit: int = 10,
    ) -> list[tuple[IngestionJob, IngestionError]]:
        _unsupported("get_recent_failures")

    def find_latest_by_source_and_kind(
        self,
        *,
        source_id: UUID,
        job_kind: IngestionJobKind,
        limit: int = 50,
    ) -> list[IngestionJob]:
        matching = [
            job
            for job in self._latest_jobs()
            if job.source_id == source_id and job.job_kind == job_kind
        ]
        matching.sort(key=lambda job: job.triggered_at, reverse=True)
        return matching[:limit]

    def find_active_pipeline_job_for_source(
        self,
        *,
        source_id: UUID,
        exclude_run_id: str | None = None,
    ) -> IngestionJob | None:
        for job in self.find_latest_by_source_and_kind(
            source_id=source_id,
            job_kind=IngestionJobKind.PIPELINE_ORCHESTRATION,
            limit=200,
        ):
            if job.status not in {IngestionStatus.PENDING, IngestionStatus.RUNNING}:
                continue
            queue_status = self._queue_status(job)
            if queue_status not in {"queued", "retrying", "running"}:
                continue
            if exclude_run_id is not None and self._run_id(job) == exclude_run_id:
                continue
            return job
        return None

    def count_active_pipeline_queue_jobs(self) -> int:
        return sum(
            1
            for job in self._latest_jobs()
            if job.job_kind == IngestionJobKind.PIPELINE_ORCHESTRATION
            and job.status == IngestionStatus.PENDING
            and self._queue_status(job) in {"queued", "retrying"}
        )

    def claim_next_pipeline_job(
        self,
        *,
        worker_id: str,
        as_of: datetime,
    ) -> IngestionJob | None:
        candidates = sorted(
            (
                job
                for job in self._latest_jobs()
                if job.job_kind == IngestionJobKind.PIPELINE_ORCHESTRATION
                and job.status == IngestionStatus.PENDING
                and self._queue_status(job) in {"queued", "retrying"}
            ),
            key=lambda job: job.triggered_at,
        )
        for job in candidates:
            next_attempt_raw = self._pipeline_payload(job).get("next_attempt_at")
            if isinstance(next_attempt_raw, str) and next_attempt_raw.strip():
                next_attempt_at = datetime.fromisoformat(next_attempt_raw.strip())
                normalized_next_attempt_at = (
                    next_attempt_at
                    if next_attempt_at.tzinfo is not None
                    else next_attempt_at.replace(tzinfo=UTC)
                )
                if normalized_next_attempt_at > as_of:
                    continue
            updated = job.model_copy(
                update={
                    "status": IngestionStatus.RUNNING,
                    "started_at": as_of,
                    "completed_at": None,
                    "metadata": self._update_pipeline_metadata(
                        job,
                        status="running",
                        queue_status="running",
                        worker_id=worker_id,
                        heartbeat_at=as_of.isoformat(timespec="seconds"),
                        updated_at=as_of.isoformat(timespec="seconds"),
                        next_attempt_at=None,
                    ),
                },
            )
            return self.save(updated)
        return None

    def heartbeat_pipeline_job(
        self,
        *,
        job_id: UUID,
        worker_id: str,
        heartbeat_at: datetime,
    ) -> IngestionJob | None:
        job = self.find_by_id(job_id)
        if job is None or job.status != IngestionStatus.RUNNING:
            return None
        current_worker_id = self._pipeline_payload(job).get("worker_id")
        if isinstance(current_worker_id, str) and current_worker_id != worker_id:
            return None
        updated = job.model_copy(
            update={
                "metadata": self._update_pipeline_metadata(
                    job,
                    worker_id=worker_id,
                    heartbeat_at=heartbeat_at.isoformat(timespec="seconds"),
                    updated_at=heartbeat_at.isoformat(timespec="seconds"),
                ),
            },
        )
        return self.save(updated)

    def mark_pipeline_job_retryable(
        self,
        *,
        job_id: UUID,
        worker_id: str,
        next_attempt_at: datetime,
        last_error: str,
        error_category: str | None,
    ) -> IngestionJob | None:
        job = self.find_by_id(job_id)
        if job is None:
            return None
        attempt_count_raw = self._pipeline_payload(job).get("attempt_count")
        attempt_count = attempt_count_raw if isinstance(attempt_count_raw, int) else 0
        updated = job.model_copy(
            update={
                "status": IngestionStatus.PENDING,
                "started_at": None,
                "completed_at": None,
                "metrics": JobMetrics(),
                "errors": [],
                "metadata": self._update_pipeline_metadata(
                    job,
                    status="retrying",
                    queue_status="retrying",
                    worker_id=worker_id,
                    next_attempt_at=next_attempt_at.isoformat(timespec="seconds"),
                    last_error=last_error,
                    error_category=error_category,
                    attempt_count=attempt_count + 1,
                    updated_at=datetime.now(UTC).isoformat(timespec="seconds"),
                ),
            },
        )
        return self.save(updated)

    def cancel_job(self, job_id: UUID) -> IngestionJob | None:
        job = self.find_by_id(job_id)
        if job is None:
            return None
        cancelled = job.cancel()
        updated = cancelled.model_copy(
            update={
                "metadata": self._update_pipeline_metadata(
                    cancelled,
                    status="cancelled",
                    queue_status="cancelled",
                    updated_at=datetime.now(UTC).isoformat(timespec="seconds"),
                ),
            },
        )
        return self.save(updated)


def _coerce_json_object(raw_value: object) -> JSONObject:
    if not isinstance(raw_value, dict):
        msg = "Expected JSON object metadata payload"
        raise TypeError(msg)
    return {str(key): to_json_value(value) for key, value in raw_value.items()}


def test_enqueue_run_persists_queue_metadata() -> None:
    source_id = uuid4()
    research_space_id = uuid4()
    repository = StubPipelineRunRepository()
    service = PipelineOrchestrationService(
        dependencies=PipelineOrchestrationDependencies(
            ingestion_scheduling_service=StubIngestionSchedulingService(
                StubIngestionSummary(source_id=source_id),
            ),
            content_enrichment_service=StubContentEnrichmentService(
                StubEnrichmentSummary(),
            ),
            entity_recognition_service=StubEntityRecognitionService(
                StubExtractionSummary(),
            ),
            pipeline_run_repository=repository,
        ),
    )

    accepted = service.enqueue_run(
        source_id=source_id,
        research_space_id=research_space_id,
        run_id="queued-run-001",
        resume_from_stage="enrichment",
        source_type="pubmed",
        graph_seed_entity_ids=["seed-1"],
    )

    assert accepted.status == "queued"
    job = repository.find_by_source(source_id)[0]
    assert job.job_kind == IngestionJobKind.PIPELINE_ORCHESTRATION
    assert job.status == IngestionStatus.PENDING
    pipeline_run = _coerce_json_object(job.metadata.get("pipeline_run"))
    requested_args = _coerce_json_object(pipeline_run.get("requested_args"))
    assert pipeline_run.get("status") == "queued"
    assert pipeline_run.get("queue_status") == "queued"
    assert pipeline_run.get("attempt_count") == 0
    assert requested_args.get("resume_from_stage") == "enrichment"
    assert requested_args.get("source_type") == "pubmed"
    assert requested_args.get("graph_seed_entity_ids") == ["seed-1"]


def test_enqueue_run_rejects_when_active_pipeline_exists() -> None:
    source_id = uuid4()
    research_space_id = uuid4()
    repository = StubPipelineRunRepository()
    service = PipelineOrchestrationService(
        dependencies=PipelineOrchestrationDependencies(
            ingestion_scheduling_service=StubIngestionSchedulingService(
                StubIngestionSummary(source_id=source_id),
            ),
            content_enrichment_service=StubContentEnrichmentService(
                StubEnrichmentSummary(),
            ),
            entity_recognition_service=StubEntityRecognitionService(
                StubExtractionSummary(),
            ),
            pipeline_run_repository=repository,
        ),
    )

    service.enqueue_run(
        source_id=source_id,
        research_space_id=research_space_id,
        run_id="queued-run-001",
    )

    with pytest.raises(ActivePipelineRunExistsError):
        service.enqueue_run(
            source_id=source_id,
            research_space_id=research_space_id,
            run_id="queued-run-002",
        )


def test_enqueue_run_rejects_when_queue_is_full(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MED13_PIPELINE_QUEUE_MAX_SIZE", "1")
    repository = StubPipelineRunRepository()
    first_source_id = uuid4()
    second_source_id = uuid4()
    research_space_id = uuid4()
    service = PipelineOrchestrationService(
        dependencies=PipelineOrchestrationDependencies(
            ingestion_scheduling_service=StubIngestionSchedulingService(
                StubIngestionSummary(source_id=first_source_id),
            ),
            content_enrichment_service=StubContentEnrichmentService(
                StubEnrichmentSummary(),
            ),
            entity_recognition_service=StubEntityRecognitionService(
                StubExtractionSummary(),
            ),
            pipeline_run_repository=repository,
        ),
    )

    service.enqueue_run(
        source_id=first_source_id,
        research_space_id=research_space_id,
        run_id="queued-run-001",
    )

    with pytest.raises(PipelineQueueFullError):
        service.enqueue_run(
            source_id=second_source_id,
            research_space_id=research_space_id,
            run_id="queued-run-002",
        )


@pytest.mark.asyncio
async def test_run_for_source_records_stage_checkpoints_with_run_id() -> None:
    source_id = uuid4()
    research_space_id = uuid4()
    repository = StubPipelineRunRepository()
    ingestion_service = StubIngestionSchedulingService(
        StubIngestionSummary(source_id=source_id),
    )
    enrichment_service = StubContentEnrichmentService(StubEnrichmentSummary())
    extraction_service = StubEntityRecognitionService(StubExtractionSummary())
    graph_service = StubGraphConnectionService(
        StubGraphOutcome(persisted_relations_count=2),
    )

    service = PipelineOrchestrationService(
        dependencies=PipelineOrchestrationDependencies(
            ingestion_scheduling_service=ingestion_service,
            content_enrichment_service=enrichment_service,
            entity_recognition_service=extraction_service,
            graph_connection_service=graph_service,
            pipeline_run_repository=repository,
        ),
    )

    summary = await service.run_for_source(
        source_id=source_id,
        research_space_id=research_space_id,
        run_id="run-001",
        source_type="clinvar",
        graph_seed_entity_ids=["seed-1"],
    )

    assert summary.status == "completed"
    assert summary.metadata is not None
    assert isinstance(summary.metadata.get("pipeline_run_checkpoint_id"), str)
    assert summary.metadata.get("query_generation_execution_mode") == "ai"
    assert summary.metadata.get("enrichment_ai_runs") == 1
    assert enrichment_service.calls[0]["pipeline_run_id"] == "run-001"
    assert extraction_service.calls[0]["pipeline_run_id"] == "run-001"
    assert graph_service.calls[0]["pipeline_run_id"] == "run-001"

    jobs = repository.find_by_source(source_id)
    assert len(jobs) == 1
    job = jobs[0]
    assert job.status == IngestionStatus.COMPLETED

    pipeline_run = _coerce_json_object(job.metadata.get("pipeline_run"))
    checkpoints = _coerce_json_object(pipeline_run.get("checkpoints"))

    assert pipeline_run.get("run_id") == "run-001"
    assert pipeline_run.get("status") == "completed"
    assert (
        _coerce_json_object(checkpoints.get("ingestion")).get("status") == "completed"
    )
    assert (
        _coerce_json_object(checkpoints.get("enrichment")).get("status") == "completed"
    )
    assert (
        _coerce_json_object(checkpoints.get("extraction")).get("status") == "completed"
    )
    assert _coerce_json_object(checkpoints.get("graph")).get("status") == "completed"


@pytest.mark.asyncio
async def test_run_for_source_records_ingestion_scope_and_total_persisted_relations() -> (
    None
):
    source_id = uuid4()
    research_space_id = uuid4()
    ingestion_job_id = uuid4()
    repository = StubPipelineRunRepository()
    ingestion_service = StubIngestionSchedulingService(
        StubIngestionSummary(
            source_id=source_id,
            ingestion_job_id=ingestion_job_id,
        ),
    )
    enrichment_service = StubContentEnrichmentService(StubEnrichmentSummary())
    extraction_service = StubEntityRecognitionService(
        StubExtractionSummary(
            persisted_relations_count=5,
            concept_members_created_count=4,
            concept_aliases_created_count=6,
            concept_decisions_proposed_count=1,
        ),
    )
    graph_service = StubGraphConnectionService(
        StubGraphOutcome(persisted_relations_count=2),
    )

    service = PipelineOrchestrationService(
        dependencies=PipelineOrchestrationDependencies(
            ingestion_scheduling_service=ingestion_service,
            content_enrichment_service=enrichment_service,
            entity_recognition_service=extraction_service,
            graph_connection_service=graph_service,
            pipeline_run_repository=repository,
        ),
    )

    summary = await service.run_for_source(
        source_id=source_id,
        research_space_id=research_space_id,
        run_id="run-scope-001",
        source_type="pubmed",
        graph_seed_entity_ids=["seed-1"],
    )

    assert summary.graph_persisted_relations == 7

    jobs = repository.find_by_source(source_id)
    assert len(jobs) == 1
    pipeline_run = _coerce_json_object(jobs[0].metadata.get("pipeline_run"))
    run_scope = _coerce_json_object(pipeline_run.get("run_scope"))
    extraction_run = _coerce_json_object(pipeline_run.get("extraction_run"))
    graph_progress = _coerce_json_object(pipeline_run.get("graph_progress"))

    assert run_scope.get("ingestion_job_id") == str(ingestion_job_id)
    assert extraction_run.get("status") == "completed"
    assert extraction_run.get("processed") == 3
    assert extraction_run.get("completed") == 3
    assert extraction_run.get("failed") == 0
    assert graph_progress.get("persisted_relations") == 7
    assert graph_progress.get("extraction_processed") == 3
    assert graph_progress.get("extraction_completed") == 3
    assert graph_progress.get("extraction_failed") == 0
    assert graph_progress.get("extraction_persisted_relations") == 5
    assert graph_progress.get("extraction_concept_members_created") == 4
    assert graph_progress.get("extraction_concept_aliases_created") == 6
    assert graph_progress.get("extraction_concept_decisions_proposed") == 1
    assert graph_progress.get("graph_stage_persisted_relations") == 2


@pytest.mark.asyncio
async def test_run_for_source_resume_from_extraction_skips_prior_stages() -> None:
    source_id = uuid4()
    research_space_id = uuid4()
    repository = StubPipelineRunRepository()
    ingestion_service = StubIngestionSchedulingService(
        StubIngestionSummary(source_id=source_id),
    )
    enrichment_service = StubContentEnrichmentService(StubEnrichmentSummary())
    extraction_service = StubEntityRecognitionService(StubExtractionSummary())

    service = PipelineOrchestrationService(
        dependencies=PipelineOrchestrationDependencies(
            ingestion_scheduling_service=ingestion_service,
            content_enrichment_service=enrichment_service,
            entity_recognition_service=extraction_service,
            pipeline_run_repository=repository,
        ),
    )

    summary = await service.run_for_source(
        source_id=source_id,
        research_space_id=research_space_id,
        run_id="run-resume",
        resume_from_stage="extraction",
    )

    assert summary.status == "completed"
    assert summary.ingestion_status == "skipped"
    assert summary.enrichment_status == "skipped"
    assert summary.extraction_status == "completed"
    assert summary.graph_status == "skipped"
    assert ingestion_service.calls == []
    assert enrichment_service.calls == []
    assert len(extraction_service.calls) == 1

    job = repository.find_by_source(source_id)[0]
    pipeline_run = _coerce_json_object(job.metadata.get("pipeline_run"))
    checkpoints = _coerce_json_object(pipeline_run.get("checkpoints"))

    assert pipeline_run.get("resume_from_stage") == "extraction"
    assert "ingestion" not in checkpoints
    assert "enrichment" not in checkpoints
    assert (
        _coerce_json_object(checkpoints.get("extraction")).get("status") == "completed"
    )


@pytest.mark.asyncio
async def test_run_for_source_persists_failed_stage_checkpoint() -> None:
    source_id = uuid4()
    research_space_id = uuid4()
    repository = StubPipelineRunRepository()
    ingestion_service = StubIngestionSchedulingService(
        StubIngestionSummary(source_id=source_id),
    )
    enrichment_service = StubContentEnrichmentService(
        StubEnrichmentSummary(),
        error=RuntimeError("enrichment down"),
    )
    extraction_service = StubEntityRecognitionService(StubExtractionSummary())

    service = PipelineOrchestrationService(
        dependencies=PipelineOrchestrationDependencies(
            ingestion_scheduling_service=ingestion_service,
            content_enrichment_service=enrichment_service,
            entity_recognition_service=extraction_service,
            pipeline_run_repository=repository,
        ),
    )

    summary = await service.run_for_source(
        source_id=source_id,
        research_space_id=research_space_id,
        run_id="run-failed",
    )

    assert summary.status == "failed"
    assert summary.ingestion_status == "completed"
    assert summary.enrichment_status == "failed"
    assert summary.extraction_status == "skipped"
    assert any(error.startswith("enrichment:") for error in summary.errors)

    job = repository.find_by_source(source_id)[0]
    assert job.status == IngestionStatus.FAILED
    pipeline_run = _coerce_json_object(job.metadata.get("pipeline_run"))
    checkpoints = _coerce_json_object(pipeline_run.get("checkpoints"))
    enrichment_checkpoint = _coerce_json_object(checkpoints.get("enrichment"))
    assert enrichment_checkpoint.get("status") == "failed"
    assert isinstance(enrichment_checkpoint.get("error"), str)


@pytest.mark.asyncio
async def test_run_for_source_completed_with_warnings_keeps_failed_metrics_zero() -> (
    None
):
    source_id = uuid4()
    research_space_id = uuid4()
    repository = StubPipelineRunRepository()
    ingestion_service = StubIngestionSchedulingService(
        StubIngestionSummary(source_id=source_id),
    )
    enrichment_service = StubContentEnrichmentService(
        StubEnrichmentSummary(errors=("enrichment:warning",)),
    )
    extraction_service = StubEntityRecognitionService(StubExtractionSummary())

    service = PipelineOrchestrationService(
        dependencies=PipelineOrchestrationDependencies(
            ingestion_scheduling_service=ingestion_service,
            content_enrichment_service=enrichment_service,
            entity_recognition_service=extraction_service,
            pipeline_run_repository=repository,
        ),
    )

    summary = await service.run_for_source(
        source_id=source_id,
        research_space_id=research_space_id,
        run_id="run-warning-metrics",
    )

    assert summary.status == "completed"
    assert "enrichment:warning" in summary.errors

    job = repository.find_by_source(source_id)[0]
    assert job.status == IngestionStatus.COMPLETED
    assert job.metrics is not None
    assert job.metrics.records_failed == 0


@pytest.mark.asyncio
async def test_run_for_source_marks_failed_when_extraction_watchdog_times_out(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MED13_PIPELINE_EXTRACTION_STAGE_TIMEOUT_SECONDS", "0.01")
    source_id = uuid4()
    research_space_id = uuid4()
    repository = StubPipelineRunRepository()
    ingestion_service = StubIngestionSchedulingService(
        StubIngestionSummary(source_id=source_id),
    )
    enrichment_service = StubContentEnrichmentService(StubEnrichmentSummary())
    extraction_service = SlowEntityRecognitionService(
        StubExtractionSummary(),
        delay_seconds=0.05,
    )

    service = PipelineOrchestrationService(
        dependencies=PipelineOrchestrationDependencies(
            ingestion_scheduling_service=ingestion_service,
            content_enrichment_service=enrichment_service,
            entity_recognition_service=extraction_service,
            pipeline_run_repository=repository,
        ),
    )

    summary = await service.run_for_source(
        source_id=source_id,
        research_space_id=research_space_id,
        run_id="run-extraction-watchdog-timeout",
    )

    assert summary.status == "failed"
    assert summary.extraction_status == "failed"
    assert any(
        error.startswith("extraction:stage_timeout:") for error in summary.errors
    )
    job = repository.find_by_source(source_id)[0]
    pipeline_run = _coerce_json_object(job.metadata.get("pipeline_run"))
    checkpoints = _coerce_json_object(pipeline_run.get("checkpoints"))
    extraction_checkpoint = _coerce_json_object(checkpoints.get("extraction"))
    assert extraction_checkpoint.get("status") == "failed"
    assert isinstance(extraction_checkpoint.get("error"), str)


@pytest.mark.asyncio
async def test_run_for_source_fails_pubmed_quality_gate_on_partial_extraction() -> None:
    source_id = uuid4()
    research_space_id = uuid4()
    repository = StubPipelineRunRepository()
    ingestion_service = StubIngestionSchedulingService(
        StubIngestionSummary(source_id=source_id),
    )
    enrichment_service = StubContentEnrichmentService(StubEnrichmentSummary())
    extraction_service = StubEntityRecognitionService(
        StubExtractionSummary(
            processed=4,
            extracted=1,
            failed=3,
        ),
    )
    graph_service = StubGraphConnectionService(
        StubGraphOutcome(persisted_relations_count=1),
    )

    service = PipelineOrchestrationService(
        dependencies=PipelineOrchestrationDependencies(
            ingestion_scheduling_service=ingestion_service,
            content_enrichment_service=enrichment_service,
            entity_recognition_service=extraction_service,
            graph_connection_service=graph_service,
            pipeline_run_repository=repository,
        ),
    )

    summary = await service.run_for_source(
        source_id=source_id,
        research_space_id=research_space_id,
        run_id="run-pubmed-quality-gate",
        source_type="pubmed",
        graph_seed_entity_ids=["seed-1"],
    )

    assert summary.status == "failed"
    assert summary.extraction_status == "completed"
    assert any(
        error.startswith("extraction:quality_gate_failed:") for error in summary.errors
    )
    assert summary.metadata is not None
    assert summary.metadata.get("extraction_quality_gate_failed") is True
    assert summary.metadata.get("extraction_failure_ratio") == pytest.approx(0.75)
    assert summary.metadata.get("extraction_failure_ratio_threshold") == pytest.approx(
        0.0,
    )

    job = repository.find_by_source(source_id)[0]
    assert job.status == IngestionStatus.FAILED
    pipeline_run = _coerce_json_object(job.metadata.get("pipeline_run"))
    checkpoints = _coerce_json_object(pipeline_run.get("checkpoints"))
    extraction_checkpoint = _coerce_json_object(checkpoints.get("extraction"))
    assert extraction_checkpoint.get("status") == "completed"
    assert isinstance(extraction_checkpoint.get("error"), str)


@pytest.mark.asyncio
async def test_run_for_source_classifies_capacity_failures_without_quality_gate() -> (
    None
):
    source_id = uuid4()
    research_space_id = uuid4()
    repository = StubPipelineRunRepository()
    ingestion_service = StubIngestionSchedulingService(
        StubIngestionSummary(source_id=source_id),
    )
    enrichment_service = StubContentEnrichmentService(StubEnrichmentSummary())
    extraction_service = StubEntityRecognitionService(
        StubExtractionSummary(
            processed=4,
            extracted=1,
            failed=3,
            errors=(
                "TooManyConnectionsError: remaining connection slots are reserved",
            ),
        ),
    )

    service = PipelineOrchestrationService(
        dependencies=PipelineOrchestrationDependencies(
            ingestion_scheduling_service=ingestion_service,
            content_enrichment_service=enrichment_service,
            entity_recognition_service=extraction_service,
            pipeline_run_repository=repository,
        ),
    )

    summary = await service.run_for_source(
        source_id=source_id,
        research_space_id=research_space_id,
        run_id="run-capacity-failure",
        source_type="pubmed",
    )

    assert summary.status == "failed"
    assert summary.extraction_status == "failed"
    assert summary.metadata is not None
    assert summary.metadata.get("extraction_quality_gate_failed") is False
    assert summary.metadata.get("error_category") == "capacity"
    assert not any(
        error.startswith("extraction:quality_gate_failed:") for error in summary.errors
    )


@pytest.mark.asyncio
async def test_run_next_queued_job_marks_capacity_failures_retryable() -> None:
    source_id = uuid4()
    research_space_id = uuid4()
    repository = StubPipelineRunRepository()
    service = PipelineOrchestrationService(
        dependencies=PipelineOrchestrationDependencies(
            ingestion_scheduling_service=StubIngestionSchedulingService(
                StubIngestionSummary(source_id=source_id),
            ),
            content_enrichment_service=StubContentEnrichmentService(
                StubEnrichmentSummary(),
            ),
            entity_recognition_service=StubEntityRecognitionService(
                StubExtractionSummary(
                    processed=3,
                    extracted=0,
                    failed=3,
                    errors=(
                        "TooManyConnectionsError: remaining connection slots are reserved",
                    ),
                ),
            ),
            pipeline_run_repository=repository,
        ),
    )

    service.enqueue_run(
        source_id=source_id,
        research_space_id=research_space_id,
        run_id="run-capacity-retry",
        source_type="pubmed",
    )

    ran_job = await service.run_next_queued_job(worker_id="worker-1")

    assert ran_job is True
    job = repository.find_by_source(source_id)[0]
    assert job.status == IngestionStatus.PENDING
    pipeline_run = _coerce_json_object(job.metadata.get("pipeline_run"))
    assert pipeline_run.get("status") == "retrying"
    assert pipeline_run.get("queue_status") == "retrying"
    assert pipeline_run.get("error_category") == "capacity"
    assert pipeline_run.get("attempt_count") == 1


@pytest.mark.asyncio
async def test_run_for_source_derives_graph_seeds_from_extraction() -> None:
    source_id = uuid4()
    research_space_id = uuid4()
    repository = StubPipelineRunRepository()
    ingestion_service = StubIngestionSchedulingService(
        StubIngestionSummary(source_id=source_id),
    )
    enrichment_service = StubContentEnrichmentService(StubEnrichmentSummary())
    extraction_service = StubEntityRecognitionService(
        StubExtractionSummary(
            derived_graph_seed_entity_ids=("auto-seed-1", "auto-seed-2"),
        ),
    )
    graph_service = StubGraphConnectionService(
        StubGraphOutcome(persisted_relations_count=1),
    )

    service = PipelineOrchestrationService(
        dependencies=PipelineOrchestrationDependencies(
            ingestion_scheduling_service=ingestion_service,
            content_enrichment_service=enrichment_service,
            entity_recognition_service=extraction_service,
            graph_connection_service=graph_service,
            pipeline_run_repository=repository,
        ),
    )

    summary = await service.run_for_source(
        source_id=source_id,
        research_space_id=research_space_id,
        run_id="run-derived-seeds",
        source_type="clinvar",
    )

    assert summary.graph_requested == 2
    assert summary.graph_processed == 2
    assert summary.graph_status == "completed"
    assert [call["seed_entity_id"] for call in graph_service.calls] == [
        "auto-seed-1",
        "auto-seed-2",
    ]
    assert summary.metadata is not None
    assert summary.metadata.get("graph_seed_mode") == "derived_from_extraction"


@pytest.mark.asyncio
async def test_run_for_source_infers_graph_seeds_from_ai_context() -> None:
    source_id = uuid4()
    research_space_id = uuid4()
    repository = StubPipelineRunRepository()
    ingestion_service = StubIngestionSchedulingService(
        StubIngestionSummary(source_id=source_id),
    )
    enrichment_service = StubContentEnrichmentService(StubEnrichmentSummary())
    extraction_service = StubEntityRecognitionService(
        StubExtractionSummary(
            derived_graph_seed_entity_ids=(),
        ),
    )
    graph_service = StubGraphConnectionService(
        StubGraphOutcome(persisted_relations_count=1),
    )
    graph_search_service = StubGraphSearchService(
        StubGraphSearchContract(
            results=(
                StubGraphSearchResultEntry(entity_id="ai-seed-1"),
                StubGraphSearchResultEntry(entity_id="ai-seed-2"),
            ),
        ),
    )

    service = PipelineOrchestrationService(
        dependencies=PipelineOrchestrationDependencies(
            ingestion_scheduling_service=ingestion_service,
            content_enrichment_service=enrichment_service,
            entity_recognition_service=extraction_service,
            graph_connection_service=graph_service,
            graph_search_service=graph_search_service,
            pipeline_run_repository=repository,
        ),
    )

    summary = await service.run_for_source(
        source_id=source_id,
        research_space_id=research_space_id,
        run_id="run-ai-seeds",
        source_type="clinvar",
    )

    assert summary.graph_requested == 2
    assert summary.graph_processed == 2
    assert summary.graph_status == "completed"
    assert [call["seed_entity_id"] for call in graph_service.calls] == [
        "ai-seed-1",
        "ai-seed-2",
    ]
    assert len(graph_search_service.calls) == 1
    assert graph_search_service.calls[0]["force_agent"] is True
    assert summary.metadata is not None
    assert summary.metadata.get("graph_seed_mode") == "ai_inferred_from_context"
