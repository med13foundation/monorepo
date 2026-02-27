"""Integration tests for production scheduler runtime semantics."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, cast
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from src.application.services.extraction_queue_service import (
    ExtractionEnqueueSummary,
    ExtractionQueueService,
)
from src.application.services.extraction_runner_service import (
    ExtractionRunnerService,
    ExtractionRunSummary,
)
from src.application.services.ingestion_scheduling_service import (
    IngestionSchedulingOptions,
    IngestionSchedulingService,
)
from src.domain.entities.ingestion_job import IngestionStatus
from src.domain.entities.ingestion_source_lock import IngestionSourceLock
from src.domain.entities.user_data_source import SourceType, UserDataSource
from src.domain.services.pubmed_ingestion import PubMedIngestionSummary
from src.infrastructure.repositories import (
    SqlAlchemyIngestionJobRepository,
    SqlAlchemyIngestionSourceLockRepository,
    SqlAlchemyUserDataSourceRepository,
)
from src.infrastructure.scheduling import PostgresScheduler
from src.models.database import Base, UserDataSourceModel

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Iterator
    from pathlib import Path

    from sqlalchemy.engine import Engine

    from src.domain.services.ingestion import (
        IngestionExtractionTarget,
        IngestionRunContext,
        IngestionRunSummary,
    )


@dataclass(frozen=True)
class _RuntimeContext:
    session_factory: sessionmaker[Session]
    engine: Engine


class _NoopExtractionQueueService:
    def enqueue_for_ingestion(
        self,
        *,
        source_id: UUID,
        ingestion_job_id: UUID,
        targets: list[IngestionExtractionTarget],
        extraction_version: int | None = None,
    ) -> ExtractionEnqueueSummary:
        resolved_version = extraction_version if extraction_version is not None else 1
        return ExtractionEnqueueSummary(
            source_id=source_id,
            ingestion_job_id=ingestion_job_id,
            extraction_version=resolved_version,
            requested=len(targets),
            queued=0,
            skipped=len(targets),
        )


class _NoopExtractionRunnerService:
    def __init__(self, *, source_types: set[str]) -> None:
        self._source_types = {value.strip().lower() for value in source_types if value}

    def has_processor_for_source_type(self, source_type: str) -> bool:
        return source_type.strip().lower() in self._source_types

    async def run_for_ingestion_job(
        self,
        *,
        source_id: UUID,
        ingestion_job_id: UUID,
        expected_items: int,
        batch_size: int | None = None,
    ) -> ExtractionRunSummary:
        _ = batch_size
        now = datetime.now(UTC)
        return ExtractionRunSummary(
            source_id=source_id,
            ingestion_job_id=ingestion_job_id,
            requested=expected_items,
            processed=0,
            completed=0,
            skipped=expected_items,
            failed=0,
            started_at=now,
            completed_at=now,
        )


@pytest.fixture
def runtime_context(tmp_path: Path) -> Iterator[_RuntimeContext]:
    db_path = tmp_path / "scheduler_runtime.sqlite"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    try:
        yield _RuntimeContext(session_factory=session_factory, engine=engine)
    finally:
        engine.dispose()


def _seed_source(session_factory: sessionmaker[Session], *, name: str) -> UUID:
    source_id = uuid4()
    with session_factory() as session:
        session.add(
            UserDataSourceModel(
                id=str(source_id),
                owner_id=str(uuid4()),
                research_space_id=None,
                name=name,
                description="",
                source_type="pubmed",
                template_id=None,
                configuration={"metadata": {"query": "MED13"}},
                status="active",
                ingestion_schedule={
                    "enabled": True,
                    "frequency": "hourly",
                    "start_time": (datetime.now(UTC) - timedelta(hours=2)).isoformat(),
                    "timezone": "UTC",
                    "backend_job_id": None,
                },
                quality_metrics={
                    "completeness_score": None,
                    "consistency_score": None,
                    "timeliness_score": None,
                    "overall_score": None,
                    "last_assessed": None,
                    "issues_count": 0,
                },
                last_ingested_at=None,
                tags=[],
                version="1.0",
            ),
        )
        session.commit()
    return source_id


def _build_service(
    *,
    session_factory: sessionmaker[Session],
    ingestion_callable: Callable[..., Awaitable[IngestionRunSummary]],
    scheduler_stale_running_timeout_seconds: int = 300,
    ingestion_job_hard_timeout_seconds: int = 7200,
) -> tuple[IngestionSchedulingService, Session]:
    session = session_factory()
    scheduler = PostgresScheduler(session_factory=session_factory)
    source_repository = SqlAlchemyUserDataSourceRepository(session)
    job_repository = SqlAlchemyIngestionJobRepository(session)
    source_lock_repository = SqlAlchemyIngestionSourceLockRepository(session)
    queue_service = _NoopExtractionQueueService()
    runner_service = _NoopExtractionRunnerService(
        source_types={SourceType.PUBMED.value},
    )

    service = IngestionSchedulingService(
        scheduler=scheduler,
        source_repository=source_repository,
        job_repository=job_repository,
        ingestion_services={SourceType.PUBMED: ingestion_callable},
        options=IngestionSchedulingOptions(
            extraction_queue_service=cast("ExtractionQueueService", queue_service),
            extraction_runner_service=cast("ExtractionRunnerService", runner_service),
            source_lock_repository=source_lock_repository,
            scheduler_stale_running_timeout_seconds=(
                scheduler_stale_running_timeout_seconds
            ),
            ingestion_job_hard_timeout_seconds=ingestion_job_hard_timeout_seconds,
        ),
    )
    return service, session


def _build_summary(source_id: UUID) -> PubMedIngestionSummary:
    return PubMedIngestionSummary(
        source_id=source_id,
        fetched_records=1,
        parsed_publications=1,
        created_publications=1,
        updated_publications=0,
    )


@pytest.mark.asyncio
async def test_restart_durability_jobs_survive_worker_restart(
    runtime_context: _RuntimeContext,
) -> None:
    source_id = _seed_source(
        runtime_context.session_factory,
        name="Restart Durability Integration Source",
    )
    execution_count = 0

    async def ingest(
        source: UserDataSource,
        *,
        context: IngestionRunContext | None = None,
    ) -> PubMedIngestionSummary:
        nonlocal execution_count
        _ = context
        execution_count += 1
        return _build_summary(source.id)

    worker_a, session_a = _build_service(
        session_factory=runtime_context.session_factory,
        ingestion_callable=ingest,
    )
    worker_b, session_b = _build_service(
        session_factory=runtime_context.session_factory,
        ingestion_callable=ingest,
    )
    try:
        await worker_a.schedule_source(source_id)
        await worker_b.run_due_jobs(
            as_of=datetime.now(UTC) + timedelta(hours=1, seconds=5),
        )
    finally:
        session_a.close()
        session_b.close()

    assert execution_count == 1


@pytest.mark.asyncio
async def test_dual_worker_race_executes_source_once(
    runtime_context: _RuntimeContext,
) -> None:
    source_id = _seed_source(
        runtime_context.session_factory,
        name="Dual Worker Race Source",
    )
    execution_count = 0
    run_started = asyncio.Event()
    allow_completion = asyncio.Event()

    async def ingest(
        source: UserDataSource,
        *,
        context: IngestionRunContext | None = None,
    ) -> PubMedIngestionSummary:
        nonlocal execution_count
        _ = context
        execution_count += 1
        run_started.set()
        await allow_completion.wait()
        return _build_summary(source.id)

    worker_a, session_a = _build_service(
        session_factory=runtime_context.session_factory,
        ingestion_callable=ingest,
    )
    worker_b, session_b = _build_service(
        session_factory=runtime_context.session_factory,
        ingestion_callable=ingest,
    )

    try:
        await worker_a.schedule_source(source_id)
        due_as_of = datetime.now(UTC) + timedelta(hours=1, seconds=5)
        run_task_a = asyncio.create_task(worker_a.run_due_jobs(as_of=due_as_of))
        run_task_b = asyncio.create_task(worker_b.run_due_jobs(as_of=due_as_of))
        await asyncio.wait_for(run_started.wait(), timeout=2)
        allow_completion.set()
        await asyncio.gather(run_task_a, run_task_b)
    finally:
        session_a.close()
        session_b.close()

    assert execution_count == 1
    with runtime_context.session_factory() as verification_session:
        job_repository = SqlAlchemyIngestionJobRepository(verification_session)
        jobs = job_repository.find_by_source(source_id, limit=25)
        assert len(jobs) == 1
        assert jobs[0].status == IngestionStatus.COMPLETED


@pytest.mark.asyncio
async def test_stale_lock_takeover_allows_new_run(
    runtime_context: _RuntimeContext,
) -> None:
    source_id = _seed_source(
        runtime_context.session_factory,
        name="Stale Lock Takeover Source",
    )
    with runtime_context.session_factory() as session:
        lock_repository = SqlAlchemyIngestionSourceLockRepository(session)
        lock_repository.upsert(
            IngestionSourceLock(
                source_id=source_id,
                lock_token="stale-lock-token",
                lease_expires_at=datetime.now(UTC) - timedelta(minutes=5),
                last_heartbeat_at=datetime.now(UTC) - timedelta(minutes=6),
                acquired_by="worker-a",
            ),
        )

    async def ingest(
        source: UserDataSource,
        *,
        context: IngestionRunContext | None = None,
    ) -> PubMedIngestionSummary:
        _ = context
        return _build_summary(source.id)

    worker, worker_session = _build_service(
        session_factory=runtime_context.session_factory,
        ingestion_callable=ingest,
    )
    try:
        summary = await worker.trigger_ingestion(source_id)
    finally:
        worker_session.close()

    assert summary.created_publications == 1
    with runtime_context.session_factory() as verification_session:
        lock_repository = SqlAlchemyIngestionSourceLockRepository(verification_session)
        assert lock_repository.get_by_source(source_id) is None


@pytest.mark.asyncio
async def test_timeout_failure_path_persists_timeout_metadata(
    runtime_context: _RuntimeContext,
) -> None:
    source_id = _seed_source(
        runtime_context.session_factory,
        name="Timeout Failure Source",
    )

    async def slow_ingest(
        source: UserDataSource,
        *,
        context: IngestionRunContext | None = None,
    ) -> PubMedIngestionSummary:
        _ = context
        await asyncio.sleep(1.2)
        return _build_summary(source.id)

    worker, worker_session = _build_service(
        session_factory=runtime_context.session_factory,
        ingestion_callable=slow_ingest,
        ingestion_job_hard_timeout_seconds=1,
    )
    try:
        with pytest.raises(TimeoutError):
            await worker.trigger_ingestion(source_id)
    finally:
        worker_session.close()

    with runtime_context.session_factory() as verification_session:
        job_repository = SqlAlchemyIngestionJobRepository(verification_session)
        jobs = job_repository.find_by_source(source_id, limit=25)
        assert jobs
        latest = jobs[0]
        assert latest.status == IngestionStatus.FAILED
        assert latest.errors
        failure_error = latest.errors[-1]
        assert failure_error.error_type == "timeout"
        assert failure_error.error_details.get("timeout_scope") == (
            "ingestion_job_hard_timeout"
        )
        failure_metadata = latest.metadata.get("failure")
        assert isinstance(failure_metadata, dict)
        assert failure_metadata.get("error_type") == "timeout"
