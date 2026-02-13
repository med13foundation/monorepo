"""Tests for the ingestion scheduling service."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, NoReturn
from uuid import UUID, uuid4

import pytest

from src.application.services.ingestion_scheduling_service import (
    IngestionSchedulingOptions,
    IngestionSchedulingService,
)
from src.application.services.pubmed_discovery_service import (
    PUBMED_STORAGE_METADATA_ARTICLE_ID_KEY,
    PUBMED_STORAGE_METADATA_JOB_ID_KEY,
    PUBMED_STORAGE_METADATA_OWNER_ID_KEY,
    PUBMED_STORAGE_METADATA_RETRYABLE_KEY,
    PUBMED_STORAGE_METADATA_USE_CASE_KEY,
    PubMedDiscoveryService,
    PubmedDownloadRequest,
)
from src.domain.entities.data_discovery_parameters import AdvancedQueryParameters
from src.domain.entities.discovery_preset import DiscoveryProvider
from src.domain.entities.discovery_search_job import (
    DiscoverySearchJob,
    DiscoverySearchStatus,
)
from src.domain.entities.ingestion_job import (
    IngestionJob,
    IngestionStatus,
    IngestionTrigger,
)
from src.domain.entities.source_record_ledger import (
    SourceRecordLedgerEntry,  # noqa: TC001
)
from src.domain.entities.source_sync_state import (
    CheckpointKind,
    SourceSyncState,
)  # noqa: TC001
from src.domain.entities.user_data_source import (
    IngestionSchedule,
    ScheduleFrequency,
    SourceConfiguration,
    SourceStatus,
    SourceType,
    UserDataSource,
)
from src.domain.repositories.ingestion_job_repository import IngestionJobRepository
from src.domain.repositories.source_record_ledger_repository import (
    SourceRecordLedgerRepository,
)
from src.domain.repositories.source_sync_state_repository import (
    SourceSyncStateRepository,
)
from src.domain.repositories.storage_repository import StorageOperationRepository
from src.domain.repositories.user_data_source_repository import UserDataSourceRepository
from src.domain.services.ingestion import IngestionRunContext  # noqa: TC001
from src.domain.services.pubmed_ingestion import PubMedIngestionSummary
from src.domain.value_objects.provenance import DataSource as ProvenanceSource
from src.domain.value_objects.provenance import Provenance
from src.infrastructure.scheduling import InMemoryScheduler
from src.type_definitions.storage import (
    StorageOperationRecord,
    StorageOperationStatus,
    StorageOperationType,
    StorageProviderTestResult,
    StorageUsageMetrics,
    StorageUseCase,
)

if TYPE_CHECKING:
    from src.domain.entities.ingestion_job import IngestionError, JobMetrics
    from src.domain.entities.storage_configuration import (
        StorageHealthSnapshot,
        StorageOperation,
    )
    from src.domain.entities.user_data_source import QualityMetrics
    from src.type_definitions.common import JSONObject, StatisticsResponse


def _unsupported(method_name: str) -> NoReturn:
    raise NotImplementedError(f"{method_name} is not implemented in test stub")


class StubSourceRepository(UserDataSourceRepository):
    def __init__(self, source: UserDataSource) -> None:
        self.source = source
        self.ingestion_recorded = False

    def save(self, source: UserDataSource) -> UserDataSource:
        self.source = source
        return source

    def find_by_id(self, source_id: UUID) -> UserDataSource | None:
        return self.source if source_id == self.source.id else None

    def find_by_owner(
        self,
        owner_id: UUID,
        skip: int = 0,
        limit: int = 50,
    ) -> list[UserDataSource]:
        _unsupported("find_by_owner")

    def find_by_type(
        self,
        source_type: SourceType,
        skip: int = 0,
        limit: int = 50,
    ) -> list[UserDataSource]:
        _unsupported("find_by_type")

    def find_by_status(
        self,
        status: SourceStatus,
        skip: int = 0,
        limit: int = 50,
    ) -> list[UserDataSource]:
        _unsupported("find_by_status")

    def find_active_sources(
        self,
        skip: int = 0,
        limit: int = 50,
    ) -> list[UserDataSource]:
        _unsupported("find_active_sources")

    def find_by_tag(
        self,
        tag: str,
        skip: int = 0,
        limit: int = 50,
    ) -> list[UserDataSource]:
        _unsupported("find_by_tag")

    def search_by_name(
        self,
        query: str,
        owner_id: UUID | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> list[UserDataSource]:
        _unsupported("search_by_name")

    def update_status(
        self,
        source_id: UUID,
        status: SourceStatus,
    ) -> UserDataSource | None:
        _unsupported("update_status")

    def update_quality_metrics(
        self,
        source_id: UUID,
        metrics: QualityMetrics,
    ) -> UserDataSource | None:
        _unsupported("update_quality_metrics")

    def update_configuration(
        self,
        source_id: UUID,
        config: SourceConfiguration,
    ) -> UserDataSource | None:
        _unsupported("update_configuration")

    def update_ingestion_schedule(
        self,
        source_id: UUID,
        schedule: IngestionSchedule,
    ) -> UserDataSource:
        self.source = self.source.update_ingestion_schedule(schedule)
        return self.source

    def record_ingestion(self, source_id: UUID) -> UserDataSource:
        self.ingestion_recorded = True
        return self.source

    def delete(self, source_id: UUID) -> bool:
        _unsupported("delete")

    def count_by_owner(self, owner_id: UUID) -> int:
        _unsupported("count_by_owner")

    def count_by_status(self, status: SourceStatus) -> int:
        _unsupported("count_by_status")

    def count_by_type(self, source_type: SourceType) -> int:
        _unsupported("count_by_type")

    def exists(self, source_id: UUID) -> bool:
        _unsupported("exists")

    def get_statistics(self) -> StatisticsResponse:
        _unsupported("get_statistics")


class StubJobRepository(IngestionJobRepository):
    def __init__(self, initial_jobs: list[IngestionJob] | None = None) -> None:
        self.saved: list[IngestionJob] = list(initial_jobs or [])

    def save(self, job: IngestionJob) -> IngestionJob:
        self.saved.append(job)
        return job

    def find_by_id(self, job_id: UUID) -> IngestionJob | None:
        _unsupported("find_by_id")

    def find_by_source(
        self,
        source_id: UUID,
        skip: int = 0,
        limit: int = 50,
    ) -> list[IngestionJob]:
        matching = [job for job in self.saved if job.source_id == source_id]
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
        _unsupported("find_by_status")

    def find_running_jobs(
        self,
        skip: int = 0,
        limit: int = 50,
    ) -> list[IngestionJob]:
        _unsupported("find_running_jobs")

    def find_failed_jobs(
        self,
        since: datetime | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> list[IngestionJob]:
        _unsupported("find_failed_jobs")

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

    def add_error(
        self,
        job_id: UUID,
        error: IngestionError,
    ) -> IngestionJob | None:
        _unsupported("add_error")

    def start_job(self, job_id: UUID) -> IngestionJob | None:
        _unsupported("start_job")

    def complete_job(
        self,
        job_id: UUID,
        metrics: JobMetrics,
    ) -> IngestionJob | None:
        _unsupported("complete_job")

    def fail_job(
        self,
        job_id: UUID,
        error: IngestionError,
    ) -> IngestionJob | None:
        _unsupported("fail_job")

    def cancel_job(self, job_id: UUID) -> IngestionJob | None:
        _unsupported("cancel_job")

    def delete_old_jobs(self, days: int = 90) -> int:
        _unsupported("delete_old_jobs")

    def count_by_source(self, source_id: UUID) -> int:
        _unsupported("count_by_source")

    def count_by_status(self, status: IngestionStatus) -> int:
        _unsupported("count_by_status")

    def count_by_trigger(self, trigger: IngestionTrigger) -> int:
        _unsupported("count_by_trigger")

    def exists(self, job_id: UUID) -> bool:
        _unsupported("exists")

    def get_job_statistics(self, source_id: UUID | None = None) -> JSONObject:
        _unsupported("get_job_statistics")

    def get_recent_failures(
        self,
        limit: int = 10,
    ) -> list[tuple[IngestionJob, IngestionError]]:
        _unsupported("get_recent_failures")


class StubPubMedIngestionService:
    def __init__(self) -> None:
        self.calls: list[UserDataSource] = []

    async def ingest(self, source: UserDataSource) -> PubMedIngestionSummary:
        self.calls.append(source)
        return PubMedIngestionSummary(
            source_id=source.id,
            fetched_records=2,
            parsed_publications=2,
            created_publications=1,
            updated_publications=1,
        )


class StubSourceSyncStateRepository(SourceSyncStateRepository):
    def __init__(self) -> None:
        self.by_source: dict[UUID, SourceSyncState] = {}

    def get_by_source(self, source_id: UUID) -> SourceSyncState | None:
        return self.by_source.get(source_id)

    def list_by_source_type(
        self,
        source_type: SourceType,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[SourceSyncState]:
        all_states = [
            state
            for state in self.by_source.values()
            if state.source_type == source_type
        ]
        return all_states[offset : offset + limit]

    def upsert(self, state: SourceSyncState) -> SourceSyncState:
        self.by_source[state.source_id] = state
        return state

    def delete_by_source(self, source_id: UUID) -> bool:
        return self.by_source.pop(source_id, None) is not None


class StubSourceRecordLedgerRepository(SourceRecordLedgerRepository):
    def __init__(self, delete_return_value: int = 0) -> None:
        self.delete_return_value = delete_return_value
        self.delete_calls: list[tuple[datetime, int]] = []

    def get_entry(
        self,
        *,
        source_id: UUID,
        external_record_id: str,
    ) -> SourceRecordLedgerEntry | None:
        return None

    def get_entries_by_external_ids(
        self,
        *,
        source_id: UUID,
        external_record_ids: list[str],
    ) -> dict[str, SourceRecordLedgerEntry]:
        return {}

    def upsert_entries(
        self,
        entries: list[SourceRecordLedgerEntry],
    ) -> list[SourceRecordLedgerEntry]:
        return entries

    def delete_by_source(self, source_id: UUID) -> int:
        return 0

    def count_for_source(self, source_id: UUID) -> int:
        return 0

    def delete_entries_older_than(
        self,
        *,
        cutoff: datetime,
        limit: int = 1000,
    ) -> int:
        self.delete_calls.append((cutoff, limit))
        return self.delete_return_value


class ContextAwarePubMedIngestionService:
    def __init__(self) -> None:
        self.contexts: list[IngestionRunContext] = []

    async def ingest(
        self,
        source: UserDataSource,
        *,
        context: IngestionRunContext | None = None,
    ) -> PubMedIngestionSummary:
        assert context is not None
        self.contexts.append(context)
        checkpoint_before = dict(context.source_sync_state.checkpoint_payload)
        return PubMedIngestionSummary(
            source_id=source.id,
            fetched_records=2,
            parsed_publications=1,
            created_publications=1,
            updated_publications=0,
            query_signature=context.query_signature,
            checkpoint_before=checkpoint_before,
            checkpoint_after={"cursor": "next-page"},
            new_records=1,
            updated_records=0,
            unchanged_records=1,
            skipped_records=1,
        )


class HighDedupPubMedIngestionService:
    async def ingest(
        self,
        source: UserDataSource,
    ) -> PubMedIngestionSummary:
        return PubMedIngestionSummary(
            source_id=source.id,
            fetched_records=20,
            parsed_publications=2,
            created_publications=1,
            updated_publications=1,
            new_records=1,
            updated_records=1,
            unchanged_records=18,
            skipped_records=18,
        )


def _build_source(schedule: IngestionSchedule) -> UserDataSource:
    return UserDataSource(
        id=uuid4(),
        owner_id=uuid4(),
        research_space_id=None,
        name="PubMed Source",
        description="",
        source_type=SourceType.PUBMED,
        template_id=None,
        configuration=SourceConfiguration(
            url=None,
            file_path=None,
            format=None,
            auth_type=None,
            auth_credentials=None,
            requests_per_minute=None,
            field_mapping=None,
            metadata={"query": "MED13"},
        ),
        status=SourceStatus.ACTIVE,
        ingestion_schedule=schedule,
        tags=[],
        last_ingested_at=None,
    )


def _build_running_job(source_id: UUID) -> IngestionJob:
    return IngestionJob(
        id=uuid4(),
        source_id=source_id,
        trigger=IngestionTrigger.SCHEDULED,
        triggered_by=None,
        status=IngestionStatus.RUNNING,
        started_at=datetime.now(UTC),
        completed_at=None,
        provenance=Provenance(
            source=ProvenanceSource.COMPUTED,
            source_version=None,
            source_url=None,
            acquired_by="test-suite",
            processing_steps=("scheduled_ingestion",),
            quality_score=None,
        ),
        metadata={},
        source_config_snapshot={},
    )


class StubStorageOperationRepository(StorageOperationRepository):
    def __init__(self, operations: list[StorageOperationRecord]) -> None:
        self.operations = operations
        self.updated: list[tuple[UUID, JSONObject]] = []

    def record_operation(
        self,
        operation: StorageOperation,
    ) -> StorageOperationRecord:
        _unsupported("record_operation")

    def list_operations(
        self,
        configuration_id: UUID,
        *,
        limit: int = 100,
    ) -> list[StorageOperationRecord]:
        _unsupported("list_operations")

    def list_failed_store_operations(
        self,
        *,
        limit: int = 100,
    ) -> list[StorageOperationRecord]:
        return self.operations[:limit]

    def update_operation_metadata(
        self,
        operation_id: UUID,
        metadata: JSONObject,
    ) -> StorageOperationRecord:
        self.updated.append((operation_id, metadata))
        for index, operation in enumerate(self.operations):
            if operation.id == operation_id:
                updated = operation.model_copy(update={"metadata": metadata})
                self.operations[index] = updated
                return updated
        message = "Operation not found"
        raise ValueError(message)

    def upsert_health_snapshot(
        self,
        snapshot: StorageHealthSnapshot,
    ) -> StorageHealthSnapshot:
        _unsupported("upsert_health_snapshot")

    def get_health_snapshot(
        self,
        configuration_id: UUID,
    ) -> StorageHealthSnapshot | None:
        _unsupported("get_health_snapshot")

    def record_test_result(
        self,
        result: StorageProviderTestResult,
    ) -> StorageProviderTestResult:
        _unsupported("record_test_result")

    def get_usage_metrics(
        self,
        configuration_id: UUID,
    ) -> StorageUsageMetrics | None:
        _unsupported("get_usage_metrics")


class StubPubMedDiscoveryRetryService(PubMedDiscoveryService):
    def __init__(self) -> None:
        self.jobs: dict[UUID, DiscoverySearchJob] = {}
        self.download_calls: list[tuple[UUID, PubmedDownloadRequest]] = []

    def set_job(
        self,
        *,
        job_id: UUID,
        owner_id: UUID,
        metadata: JSONObject,
    ) -> None:
        job = DiscoverySearchJob(
            id=job_id,
            owner_id=owner_id,
            session_id=None,
            provider=DiscoveryProvider.PUBMED,
            status=DiscoverySearchStatus.COMPLETED,
            query_preview="stub-query",
            parameters=AdvancedQueryParameters(gene_symbol=None, search_term=None),
            total_results=0,
            result_metadata=metadata,
        )
        self.jobs[job_id] = job

    def get_search_job(
        self,
        owner_id: UUID,
        job_id: UUID,
    ) -> DiscoverySearchJob | None:
        job = self.jobs.get(job_id)
        if job is None or job.owner_id != owner_id:
            return None
        return job

    async def download_article_pdf(
        self,
        owner_id: UUID,
        request: PubmedDownloadRequest,
    ) -> StorageOperationRecord:
        self.download_calls.append((owner_id, request))
        return StorageOperationRecord(
            id=uuid4(),
            configuration_id=uuid4(),
            user_id=owner_id,
            operation_type=StorageOperationType.STORE,
            key=f"discovery/pubmed/{request.job_id}/{request.article_id}.pdf",
            file_size_bytes=None,
            status=StorageOperationStatus.SUCCESS,
            error_message=None,
            metadata={},
            created_at=datetime.now(UTC),
        )


def _make_failed_operation(
    *,
    job_id: UUID,
    owner_id: UUID,
    article_id: str,
    retryable: bool = True,
) -> StorageOperationRecord:
    return StorageOperationRecord(
        id=uuid4(),
        configuration_id=uuid4(),
        user_id=owner_id,
        operation_type=StorageOperationType.STORE,
        key=f"discovery/pubmed/{job_id}/{article_id}.pdf",
        file_size_bytes=None,
        status=StorageOperationStatus.FAILED,
        error_message="upload failed",
        metadata={
            PUBMED_STORAGE_METADATA_USE_CASE_KEY: StorageUseCase.PDF.value,
            PUBMED_STORAGE_METADATA_JOB_ID_KEY: str(job_id),
            PUBMED_STORAGE_METADATA_OWNER_ID_KEY: str(owner_id),
            PUBMED_STORAGE_METADATA_ARTICLE_ID_KEY: article_id,
            PUBMED_STORAGE_METADATA_RETRYABLE_KEY: retryable,
        },
        created_at=datetime.now(UTC),
    )


@pytest.mark.asyncio
async def test_run_due_jobs_triggers_ingestion() -> None:
    schedule = IngestionSchedule(
        enabled=True,
        frequency=ScheduleFrequency.HOURLY,
        start_time=datetime.now(UTC) - timedelta(hours=1),
    )
    source = _build_source(schedule)
    source_repo = StubSourceRepository(source)
    job_repo = StubJobRepository()
    pubmed_service = StubPubMedIngestionService()
    scheduler = InMemoryScheduler()

    service = IngestionSchedulingService(
        scheduler=scheduler,
        source_repository=source_repo,
        job_repository=job_repo,
        ingestion_services={SourceType.PUBMED: pubmed_service.ingest},
    )

    await service.schedule_source(source.id)
    await service.run_due_jobs(as_of=datetime.now(UTC) + timedelta(hours=1, seconds=1))

    assert len(pubmed_service.calls) == 1
    assert source_repo.ingestion_recorded
    # Jobs saved include initial, running, completion states
    assert len(job_repo.saved) >= 3


@pytest.mark.asyncio
async def test_run_due_jobs_updates_sync_state_and_idempotency_metadata() -> None:
    schedule = IngestionSchedule(
        enabled=True,
        frequency=ScheduleFrequency.HOURLY,
        start_time=datetime.now(UTC) - timedelta(hours=1),
    )
    source = _build_source(schedule)
    source_repo = StubSourceRepository(source)
    job_repo = StubJobRepository()
    pubmed_service = ContextAwarePubMedIngestionService()
    scheduler = InMemoryScheduler()
    sync_state_repository = StubSourceSyncStateRepository()
    ledger_repository = StubSourceRecordLedgerRepository()

    service = IngestionSchedulingService(
        scheduler=scheduler,
        source_repository=source_repo,
        job_repository=job_repo,
        ingestion_services={SourceType.PUBMED: pubmed_service.ingest},
        options=IngestionSchedulingOptions(
            source_sync_state_repository=sync_state_repository,
            source_record_ledger_repository=ledger_repository,
        ),
    )

    await service.schedule_source(source.id)
    await service.run_due_jobs(as_of=datetime.now(UTC) + timedelta(hours=1, seconds=1))

    saved_state = sync_state_repository.get_by_source(source.id)
    assert saved_state is not None
    assert saved_state.last_successful_job_id is not None
    assert saved_state.query_signature is not None
    assert saved_state.checkpoint_payload == {"cursor": "next-page"}

    completed_jobs = [job for job in job_repo.saved if job.status.value == "completed"]
    assert completed_jobs
    idempotency = completed_jobs[-1].metadata.get("idempotency")
    assert isinstance(idempotency, dict)
    assert idempotency.get("checkpoint_after") == {"cursor": "next-page"}
    assert idempotency.get("new_records") == 1
    assert idempotency.get("unchanged_records") == 1


@pytest.mark.asyncio
async def test_run_due_jobs_retries_failed_pdf_downloads() -> None:
    owner_id = uuid4()
    job_id = uuid4()
    article_id = "12345"
    operation = _make_failed_operation(
        job_id=job_id,
        owner_id=owner_id,
        article_id=article_id,
    )
    storage_repo = StubStorageOperationRepository([operation])
    discovery_service = StubPubMedDiscoveryRetryService()
    discovery_service.set_job(
        job_id=job_id,
        owner_id=owner_id,
        metadata={"stored_assets": {}},
    )

    service = IngestionSchedulingService(
        scheduler=InMemoryScheduler(),
        source_repository=StubSourceRepository(
            _build_source(
                IngestionSchedule(
                    enabled=False,
                    frequency=ScheduleFrequency.MANUAL,
                ),
            ),
        ),
        job_repository=StubJobRepository(),
        ingestion_services={},
        options=IngestionSchedulingOptions(
            storage_operation_repository=storage_repo,
            pubmed_discovery_service=discovery_service,
        ),
    )

    await service.run_due_jobs()

    assert len(discovery_service.download_calls) == 1
    updated_metadata = storage_repo.updated[0][1]
    assert updated_metadata[PUBMED_STORAGE_METADATA_RETRYABLE_KEY] is False


@pytest.mark.asyncio
async def test_retry_skips_when_article_already_stored() -> None:
    owner_id = uuid4()
    job_id = uuid4()
    article_id = "55555"
    operation = _make_failed_operation(
        job_id=job_id,
        owner_id=owner_id,
        article_id=article_id,
    )
    storage_repo = StubStorageOperationRepository([operation])
    discovery_service = StubPubMedDiscoveryRetryService()
    discovery_service.set_job(
        job_id=job_id,
        owner_id=owner_id,
        metadata={"stored_assets": {article_id: "discovery/pubmed/saved.pdf"}},
    )

    service = IngestionSchedulingService(
        scheduler=InMemoryScheduler(),
        source_repository=StubSourceRepository(
            _build_source(
                IngestionSchedule(
                    enabled=False,
                    frequency=ScheduleFrequency.MANUAL,
                ),
            ),
        ),
        job_repository=StubJobRepository(),
        ingestion_services={},
        options=IngestionSchedulingOptions(
            storage_operation_repository=storage_repo,
            pubmed_discovery_service=discovery_service,
        ),
    )

    await service.run_due_jobs()

    assert not discovery_service.download_calls
    updated_metadata = storage_repo.updated[0][1]
    assert updated_metadata[PUBMED_STORAGE_METADATA_RETRYABLE_KEY] is False


@pytest.mark.asyncio
async def test_trigger_ingestion_blocks_when_source_has_running_job() -> None:
    schedule = IngestionSchedule(
        enabled=True,
        frequency=ScheduleFrequency.HOURLY,
        start_time=datetime.now(UTC) - timedelta(hours=1),
    )
    source = _build_source(schedule)
    source_repo = StubSourceRepository(source)
    job_repo = StubJobRepository(initial_jobs=[_build_running_job(source.id)])
    scheduler = InMemoryScheduler()

    service = IngestionSchedulingService(
        scheduler=scheduler,
        source_repository=source_repo,
        job_repository=job_repo,
        ingestion_services={SourceType.PUBMED: StubPubMedIngestionService().ingest},
    )

    with pytest.raises(ValueError, match="already running"):
        await service.trigger_ingestion(source.id)


@pytest.mark.asyncio
async def test_run_due_jobs_compacts_stale_ledger_entries() -> None:
    source = _build_source(
        IngestionSchedule(
            enabled=False,
            frequency=ScheduleFrequency.MANUAL,
        ),
    )
    ledger_repository = StubSourceRecordLedgerRepository(delete_return_value=7)
    service = IngestionSchedulingService(
        scheduler=InMemoryScheduler(),
        source_repository=StubSourceRepository(source),
        job_repository=StubJobRepository(),
        ingestion_services={},
        options=IngestionSchedulingOptions(
            source_record_ledger_repository=ledger_repository,
            source_ledger_retention_days=30,
            source_ledger_cleanup_batch_size=55,
        ),
    )

    await service.run_due_jobs()

    assert len(ledger_repository.delete_calls) == 1
    _, limit = ledger_repository.delete_calls[0]
    assert limit == 55


@pytest.mark.asyncio
async def test_run_due_jobs_logs_high_dedup_ratio_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    schedule = IngestionSchedule(
        enabled=True,
        frequency=ScheduleFrequency.HOURLY,
        start_time=datetime.now(UTC) - timedelta(hours=1),
    )
    source = _build_source(schedule)
    source_repo = StubSourceRepository(source)
    job_repo = StubJobRepository()
    scheduler = InMemoryScheduler()
    service = IngestionSchedulingService(
        scheduler=scheduler,
        source_repository=source_repo,
        job_repository=job_repo,
        ingestion_services={
            SourceType.PUBMED: HighDedupPubMedIngestionService().ingest,
        },
    )

    await service.schedule_source(source.id)
    with caplog.at_level(logging.WARNING):
        await service.run_due_jobs(
            as_of=datetime.now(UTC) + timedelta(hours=1, seconds=1),
        )

    assert any(
        "High dedup ratio detected for source ingestion run" in record.message
        for record in caplog.records
    )


@pytest.mark.asyncio
async def test_query_signature_change_logs_checkpoint_reset_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    schedule = IngestionSchedule(
        enabled=True,
        frequency=ScheduleFrequency.HOURLY,
        start_time=datetime.now(UTC) - timedelta(hours=1),
    )
    source = _build_source(schedule)
    source_repo = StubSourceRepository(source)
    job_repo = StubJobRepository()
    pubmed_service = ContextAwarePubMedIngestionService()
    scheduler = InMemoryScheduler()
    sync_state_repository = StubSourceSyncStateRepository()
    sync_state_repository.upsert(
        SourceSyncState(
            source_id=source.id,
            source_type=source.source_type,
            checkpoint_kind=CheckpointKind.CURSOR,
            checkpoint_payload={"retstart": 50},
            query_signature="outdated-signature",
        ),
    )

    service = IngestionSchedulingService(
        scheduler=scheduler,
        source_repository=source_repo,
        job_repository=job_repo,
        ingestion_services={SourceType.PUBMED: pubmed_service.ingest},
        options=IngestionSchedulingOptions(
            source_sync_state_repository=sync_state_repository,
            source_record_ledger_repository=StubSourceRecordLedgerRepository(),
        ),
    )

    await service.schedule_source(source.id)
    with caplog.at_level(logging.WARNING):
        await service.run_due_jobs(
            as_of=datetime.now(UTC) + timedelta(hours=1, seconds=1),
        )

    assert any(
        "Source query signature changed; resetting checkpoint payload" in record.message
        for record in caplog.records
    )
    assert pubmed_service.contexts
    assert pubmed_service.contexts[0].source_sync_state.checkpoint_payload == {}
