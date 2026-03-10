"""Tests for the ingestion scheduling service."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, NoReturn, cast
from uuid import UUID, uuid4

import pytest

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
    IngestionJobKind,
    IngestionStatus,
    IngestionTrigger,
)
from src.domain.entities.ingestion_source_lock import IngestionSourceLock  # noqa: TC001
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
from src.domain.repositories.ingestion_source_lock_repository import (
    IngestionSourceLockRepository,
)
from src.domain.repositories.source_record_ledger_repository import (
    SourceRecordLedgerRepository,
)
from src.domain.repositories.source_sync_state_repository import (
    SourceSyncStateRepository,
)
from src.domain.repositories.storage_repository import StorageOperationRepository
from src.domain.repositories.user_data_source_repository import UserDataSourceRepository
from src.domain.services.ingestion import (
    IngestionExtractionTarget,
    IngestionProgressUpdate,
    IngestionRunContext,  # noqa: TC001
)
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

    def _latest_jobs(self) -> list[IngestionJob]:
        latest_by_id: dict[UUID, IngestionJob] = {}
        for job in self.saved:
            latest_by_id[job.id] = job
        return list(latest_by_id.values())

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
        _unsupported("find_by_status")

    def find_running_jobs(
        self,
        skip: int = 0,
        limit: int = 50,
    ) -> list[IngestionJob]:
        running_jobs = [
            job for job in self._latest_jobs() if job.status == IngestionStatus.RUNNING
        ]
        running_jobs.sort(key=lambda job: job.triggered_at, reverse=True)
        return running_jobs[skip : skip + limit]

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
        for job in self._latest_jobs():
            if job.source_id != source_id:
                continue
            if job.job_kind != IngestionJobKind.PIPELINE_ORCHESTRATION:
                continue
            run_id = str(job.metadata.get("run_id", "")).strip()
            if exclude_run_id is not None and run_id == exclude_run_id:
                continue
            if job.status == IngestionStatus.RUNNING:
                return job
            queue_status = str(job.metadata.get("queue_status", "")).strip().lower()
            if queue_status in {"queued", "retrying"}:
                return job
        return None

    def count_active_pipeline_queue_jobs(self) -> int:
        count = 0
        for job in self._latest_jobs():
            if job.job_kind != IngestionJobKind.PIPELINE_ORCHESTRATION:
                continue
            queue_status = str(job.metadata.get("queue_status", "")).strip().lower()
            if queue_status in {"queued", "retrying"}:
                count += 1
        return count

    def claim_next_pipeline_job(
        self,
        *,
        worker_id: str,
        as_of: datetime,
    ) -> IngestionJob | None:
        _ = worker_id, as_of
        return None

    def heartbeat_pipeline_job(
        self,
        *,
        job_id: UUID,
        worker_id: str,
        heartbeat_at: datetime,
    ) -> IngestionJob | None:
        _ = job_id, worker_id, heartbeat_at
        return None

    def mark_pipeline_job_retryable(
        self,
        *,
        job_id: UUID,
        worker_id: str,
        next_attempt_at: datetime,
        last_error: str,
        error_category: str | None,
    ) -> IngestionJob | None:
        _ = job_id, worker_id, next_attempt_at, last_error, error_category
        return None


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


class StubExtractionQueueService:
    def __init__(self) -> None:
        self.calls: list[tuple[UUID, UUID, tuple[IngestionExtractionTarget, ...]]] = []

    def enqueue_for_ingestion(
        self,
        *,
        source_id: UUID,
        ingestion_job_id: UUID,
        targets: list[IngestionExtractionTarget],
        extraction_version: int | None = None,
    ) -> ExtractionEnqueueSummary:
        _ = extraction_version
        normalized_targets = tuple(targets)
        self.calls.append((source_id, ingestion_job_id, normalized_targets))
        return ExtractionEnqueueSummary(
            source_id=source_id,
            ingestion_job_id=ingestion_job_id,
            extraction_version=1,
            requested=len(normalized_targets),
            queued=len(normalized_targets),
            skipped=0,
        )


class StubExtractionRunnerService:
    def __init__(self, supported_source_types: set[str] | None = None) -> None:
        self.supported_source_types = {
            value.strip().lower()
            for value in (supported_source_types or set())
            if value.strip()
        }
        self.calls: list[tuple[UUID, UUID, int]] = []

    def has_processor_for_source_type(self, source_type: str) -> bool:
        return source_type.strip().lower() in self.supported_source_types

    async def run_for_ingestion_job(
        self,
        *,
        source_id: UUID,
        ingestion_job_id: UUID,
        expected_items: int,
        batch_size: int | None = None,
    ) -> ExtractionRunSummary:
        _ = batch_size
        self.calls.append((source_id, ingestion_job_id, expected_items))
        now = datetime.now(UTC)
        return ExtractionRunSummary(
            source_id=source_id,
            ingestion_job_id=ingestion_job_id,
            requested=expected_items,
            processed=expected_items,
            completed=expected_items,
            skipped=0,
            failed=0,
            started_at=now,
            completed_at=now,
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


class StubSourceLockRepository(IngestionSourceLockRepository):
    def __init__(self) -> None:
        self.by_source: dict[UUID, IngestionSourceLock] = {}
        self.refresh_calls = 0
        self.release_calls = 0

    @staticmethod
    def _normalize_datetime(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    def get_by_source(self, source_id: UUID) -> IngestionSourceLock | None:
        return self.by_source.get(source_id)

    def try_acquire(
        self,
        *,
        source_id: UUID,
        lock_token: str,
        lease_expires_at: datetime,
        heartbeat_at: datetime,
        acquired_by: str | None = None,
    ) -> IngestionSourceLock | None:
        existing = self.by_source.get(source_id)
        normalized_heartbeat = self._normalize_datetime(heartbeat_at)
        normalized_expiry = self._normalize_datetime(lease_expires_at)
        if existing is not None:
            existing_expiry = self._normalize_datetime(existing.lease_expires_at)
            if (
                existing_expiry > normalized_heartbeat
                and existing.lock_token != lock_token
            ):
                return None

        lock = IngestionSourceLock(
            source_id=source_id,
            lock_token=lock_token,
            lease_expires_at=normalized_expiry,
            last_heartbeat_at=normalized_heartbeat,
            acquired_by=acquired_by,
        )
        self.by_source[source_id] = lock
        return lock

    def refresh_lease(
        self,
        *,
        source_id: UUID,
        lock_token: str,
        lease_expires_at: datetime,
        heartbeat_at: datetime,
    ) -> IngestionSourceLock | None:
        existing = self.by_source.get(source_id)
        if existing is None or existing.lock_token != lock_token:
            return None
        self.refresh_calls += 1
        refreshed = IngestionSourceLock(
            source_id=source_id,
            lock_token=lock_token,
            lease_expires_at=self._normalize_datetime(lease_expires_at),
            last_heartbeat_at=self._normalize_datetime(heartbeat_at),
            acquired_by=existing.acquired_by,
        )
        self.by_source[source_id] = refreshed
        return refreshed

    def release(
        self,
        *,
        source_id: UUID,
        lock_token: str,
    ) -> bool:
        existing = self.by_source.get(source_id)
        if existing is None or existing.lock_token != lock_token:
            return False
        self.release_calls += 1
        self.by_source.pop(source_id, None)
        return True

    def upsert(self, lock: IngestionSourceLock) -> IngestionSourceLock:
        self.by_source[lock.source_id] = lock
        return lock

    def list_expired(
        self,
        *,
        as_of: datetime,
        limit: int = 100,
    ) -> list[IngestionSourceLock]:
        normalized_as_of = self._normalize_datetime(as_of)
        expired = [
            lock
            for lock in self.by_source.values()
            if self._normalize_datetime(lock.lease_expires_at) <= normalized_as_of
        ]
        return expired[: max(limit, 1)]

    def delete_by_source(self, source_id: UUID) -> bool:
        return self.by_source.pop(source_id, None) is not None

    def delete_expired(
        self,
        *,
        as_of: datetime,
        limit: int = 1000,
    ) -> int:
        normalized_as_of = self._normalize_datetime(as_of)
        candidates = [
            source_id
            for source_id, lock in self.by_source.items()
            if self._normalize_datetime(lock.lease_expires_at) <= normalized_as_of
        ][: max(limit, 1)]
        for source_id in candidates:
            self.by_source.pop(source_id, None)
        return len(candidates)


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


class DeterministicFallbackPubMedIngestionService:
    async def ingest(
        self,
        source: UserDataSource,
    ) -> PubMedIngestionSummary:
        return PubMedIngestionSummary(
            source_id=source.id,
            fetched_records=2,
            parsed_publications=2,
            created_publications=1,
            updated_publications=0,
            query_generation_decision="skipped",
            query_generation_execution_mode="deterministic",
            query_generation_fallback_reason=(
                "ai_query_generation_disabled_or_unavailable"
            ),
            query_generation_downstream_fetched_records=2,
            query_generation_downstream_processed_records=2,
            new_records=1,
            updated_records=0,
            unchanged_records=1,
            skipped_records=1,
        )


class SlowTimeoutPubMedIngestionService:
    async def ingest(
        self,
        source: UserDataSource,
    ) -> PubMedIngestionSummary:
        await asyncio.sleep(1.2)
        return PubMedIngestionSummary(
            source_id=source.id,
            fetched_records=1,
            parsed_publications=1,
            created_publications=1,
            updated_publications=0,
        )


class QueueingSourceIngestionService:
    def __init__(self, source_type: SourceType) -> None:
        self.source_type = source_type

    async def ingest(
        self,
        source: UserDataSource,
        *,
        context: IngestionRunContext | None = None,
    ) -> PubMedIngestionSummary:
        _ = context
        source_type_value = source.source_type.value
        extraction_target = IngestionExtractionTarget(
            source_record_id=f"{source_type_value}:record-1",
            source_type=source_type_value,
            publication_id=None,
            pubmed_id="123456" if source.source_type == SourceType.PUBMED else None,
            metadata={"raw_record": {"title": "queued"}},
        )
        return PubMedIngestionSummary(
            source_id=source.id,
            fetched_records=1,
            parsed_publications=1,
            created_publications=1,
            updated_publications=0,
            extraction_targets=(extraction_target,),
            new_records=1,
            updated_records=0,
            unchanged_records=0,
            skipped_records=0,
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


def _build_running_job(
    source_id: UUID,
    *,
    started_at: datetime | None = None,
    job_kind: IngestionJobKind = IngestionJobKind.INGESTION,
    metadata: JSONObject | None = None,
) -> IngestionJob:
    now = started_at or datetime.now(UTC)
    return IngestionJob(
        id=uuid4(),
        source_id=source_id,
        job_kind=job_kind,
        trigger=IngestionTrigger.SCHEDULED,
        triggered_by=None,
        status=IngestionStatus.RUNNING,
        started_at=now,
        completed_at=None,
        provenance=Provenance(
            source=ProvenanceSource.COMPUTED,
            source_version=None,
            source_url=None,
            acquired_by="test-suite",
            processing_steps=("scheduled_ingestion",),
            quality_score=None,
        ),
        metadata=metadata or {},
        source_config_snapshot={},
    )


def _build_completed_job(
    source_id: UUID,
    *,
    triggered_at: datetime,
    metadata: JSONObject | None = None,
) -> IngestionJob:
    started_at = triggered_at
    completed_at = triggered_at + timedelta(minutes=1)
    return IngestionJob(
        id=uuid4(),
        source_id=source_id,
        trigger=IngestionTrigger.SCHEDULED,
        triggered_by=None,
        triggered_at=triggered_at,
        status=IngestionStatus.COMPLETED,
        started_at=started_at,
        completed_at=completed_at,
        provenance=Provenance(
            source=ProvenanceSource.COMPUTED,
            source_version=None,
            source_url=None,
            acquired_by="test-suite",
            processing_steps=("scheduled_ingestion",),
            quality_score=None,
        ),
        metadata=metadata or {},
        source_config_snapshot={},
    )


def _build_ingestion_options(
    *,
    storage_operation_repository: StorageOperationRepository | None = None,
    pubmed_discovery_service: PubMedDiscoveryService | None = None,
    source_sync_state_repository: SourceSyncStateRepository | None = None,
    source_record_ledger_repository: SourceRecordLedgerRepository | None = None,
    source_lock_repository: IngestionSourceLockRepository | None = None,
    source_ledger_retention_days: int | None = 180,
    source_ledger_cleanup_batch_size: int = 1000,
    retry_batch_size: int = 25,
    scheduler_stale_running_timeout_seconds: int = 300,
    ingestion_job_hard_timeout_seconds: int = 7200,
    extraction_queue_service: StubExtractionQueueService | None = None,
    extraction_runner_service: StubExtractionRunnerService | None = None,
) -> IngestionSchedulingOptions:
    queue_service = extraction_queue_service or StubExtractionQueueService()
    runner_service = extraction_runner_service or StubExtractionRunnerService(
        {
            SourceType.PUBMED.value,
            SourceType.CLINVAR.value,
        },
    )
    return IngestionSchedulingOptions(
        storage_operation_repository=storage_operation_repository,
        pubmed_discovery_service=pubmed_discovery_service,
        extraction_queue_service=cast("ExtractionQueueService", queue_service),
        extraction_runner_service=cast("ExtractionRunnerService", runner_service),
        source_sync_state_repository=source_sync_state_repository,
        source_record_ledger_repository=source_record_ledger_repository,
        source_lock_repository=source_lock_repository,
        source_ledger_retention_days=source_ledger_retention_days,
        source_ledger_cleanup_batch_size=source_ledger_cleanup_batch_size,
        retry_batch_size=retry_batch_size,
        scheduler_stale_running_timeout_seconds=(
            scheduler_stale_running_timeout_seconds
        ),
        ingestion_job_hard_timeout_seconds=ingestion_job_hard_timeout_seconds,
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
        options=_build_ingestion_options(),
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
        options=_build_ingestion_options(
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
                    start_time=datetime.now(UTC),
                ),
            ),
        ),
        job_repository=StubJobRepository(),
        ingestion_services={},
        options=_build_ingestion_options(
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
                    start_time=datetime.now(UTC),
                ),
            ),
        ),
        job_repository=StubJobRepository(),
        ingestion_services={},
        options=_build_ingestion_options(
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
        options=_build_ingestion_options(),
    )

    with pytest.raises(ValueError, match="already running"):
        await service.trigger_ingestion(source.id)


@pytest.mark.asyncio
async def test_run_due_jobs_marks_stale_running_jobs_failed() -> None:
    source = _build_source(
        IngestionSchedule(
            enabled=False,
            frequency=ScheduleFrequency.MANUAL,
            start_time=datetime.now(UTC),
        ),
    )
    stale_job = _build_running_job(
        source.id,
        started_at=datetime.now(UTC) - timedelta(minutes=15),
    )
    job_repo = StubJobRepository(initial_jobs=[stale_job])
    service = IngestionSchedulingService(
        scheduler=InMemoryScheduler(),
        source_repository=StubSourceRepository(source),
        job_repository=job_repo,
        ingestion_services={},
        options=_build_ingestion_options(
            scheduler_stale_running_timeout_seconds=300,
            ingestion_job_hard_timeout_seconds=300,
        ),
    )

    await service.run_due_jobs(as_of=datetime.now(UTC))

    stale_revisions = [job for job in job_repo.saved if job.id == stale_job.id]
    assert stale_revisions
    latest_stale_revision = stale_revisions[-1]
    assert latest_stale_revision.status == IngestionStatus.FAILED
    assert latest_stale_revision.errors
    failure_error = latest_stale_revision.errors[-1]
    assert failure_error.error_type == "timeout"
    assert failure_error.error_details.get("timeout_scope") == "stale_running_recovery"
    failure_metadata = latest_stale_revision.metadata.get("failure")
    assert isinstance(failure_metadata, dict)
    assert failure_metadata.get("error_type") == "timeout"


@pytest.mark.asyncio
async def test_run_due_jobs_syncs_pipeline_metadata_for_stale_pipeline_jobs() -> None:
    source = _build_source(
        IngestionSchedule(
            enabled=False,
            frequency=ScheduleFrequency.MANUAL,
            start_time=datetime.now(UTC),
        ),
    )
    stale_job = _build_running_job(
        source.id,
        started_at=datetime.now(UTC) - timedelta(minutes=15),
        job_kind=IngestionJobKind.PIPELINE_ORCHESTRATION,
        metadata={
            "pipeline_run": {
                "run_id": "run-stale",
                "status": "running",
                "queue_status": "running",
                "accepted_at": "2026-03-07T02:52:02+00:00",
                "started_at": "2026-03-07T02:52:06+00:00",
                "completed_at": None,
                "updated_at": "2026-03-07T02:56:22+00:00",
            },
        },
    )
    job_repo = StubJobRepository(initial_jobs=[stale_job])
    service = IngestionSchedulingService(
        scheduler=InMemoryScheduler(),
        source_repository=StubSourceRepository(source),
        job_repository=job_repo,
        ingestion_services={},
        options=_build_ingestion_options(
            scheduler_stale_running_timeout_seconds=300,
            ingestion_job_hard_timeout_seconds=300,
        ),
    )

    await service.run_due_jobs(as_of=datetime.now(UTC))

    stale_revisions = [job for job in job_repo.saved if job.id == stale_job.id]
    assert stale_revisions
    latest_stale_revision = stale_revisions[-1]
    assert latest_stale_revision.status == IngestionStatus.FAILED
    pipeline_metadata = latest_stale_revision.metadata.get("pipeline_run")
    assert isinstance(pipeline_metadata, dict)
    assert pipeline_metadata.get("status") == "failed"
    assert pipeline_metadata.get("queue_status") == "failed"
    assert pipeline_metadata.get("completed_at") is not None
    assert pipeline_metadata.get("updated_at") is not None
    assert pipeline_metadata.get("error_category") == "timeout"
    assert isinstance(pipeline_metadata.get("last_error"), str)


@pytest.mark.asyncio
async def test_trigger_ingestion_blocks_when_source_lock_is_owned_by_another_worker() -> (
    None
):
    schedule = IngestionSchedule(
        enabled=True,
        frequency=ScheduleFrequency.HOURLY,
        start_time=datetime.now(UTC) - timedelta(hours=1),
    )
    source = _build_source(schedule)
    source_repo = StubSourceRepository(source)
    job_repo = StubJobRepository()
    source_lock_repository = StubSourceLockRepository()
    source_lock_repository.upsert(
        IngestionSourceLock(
            source_id=source.id,
            lock_token="existing-lock-token",
            lease_expires_at=datetime.now(UTC) + timedelta(minutes=5),
            last_heartbeat_at=datetime.now(UTC),
            acquired_by="worker-a",
        ),
    )

    service = IngestionSchedulingService(
        scheduler=InMemoryScheduler(),
        source_repository=source_repo,
        job_repository=job_repo,
        ingestion_services={SourceType.PUBMED: StubPubMedIngestionService().ingest},
        options=_build_ingestion_options(
            source_lock_repository=source_lock_repository,
        ),
    )

    with pytest.raises(ValueError, match="already running"):
        await service.trigger_ingestion(source.id)


@pytest.mark.asyncio
async def test_trigger_ingestion_takes_over_expired_source_lock() -> None:
    schedule = IngestionSchedule(
        enabled=True,
        frequency=ScheduleFrequency.HOURLY,
        start_time=datetime.now(UTC) - timedelta(hours=1),
    )
    source = _build_source(schedule)
    source_repo = StubSourceRepository(source)
    job_repo = StubJobRepository()
    source_lock_repository = StubSourceLockRepository()
    source_lock_repository.upsert(
        IngestionSourceLock(
            source_id=source.id,
            lock_token="stale-lock-token",
            lease_expires_at=datetime.now(UTC) - timedelta(minutes=5),
            last_heartbeat_at=datetime.now(UTC) - timedelta(minutes=6),
            acquired_by="worker-a",
        ),
    )

    service = IngestionSchedulingService(
        scheduler=InMemoryScheduler(),
        source_repository=source_repo,
        job_repository=job_repo,
        ingestion_services={SourceType.PUBMED: StubPubMedIngestionService().ingest},
        options=_build_ingestion_options(
            source_lock_repository=source_lock_repository,
        ),
    )

    summary = await service.trigger_ingestion(source.id)

    assert summary.created_publications == 1
    assert source.id not in source_lock_repository.by_source
    assert source_lock_repository.release_calls == 1


@pytest.mark.asyncio
async def test_trigger_ingestion_force_recover_does_not_steal_active_source_lock() -> (
    None
):
    schedule = IngestionSchedule(
        enabled=True,
        frequency=ScheduleFrequency.HOURLY,
        start_time=datetime.now(UTC) - timedelta(hours=1),
    )
    source = _build_source(schedule)
    source_repo = StubSourceRepository(source)
    job_repo = StubJobRepository()
    source_lock_repository = StubSourceLockRepository()
    source_lock_repository.upsert(
        IngestionSourceLock(
            source_id=source.id,
            lock_token="active-lock-token",
            lease_expires_at=datetime.now(UTC) + timedelta(minutes=5),
            last_heartbeat_at=datetime.now(UTC),
            acquired_by="worker-a",
        ),
    )

    service = IngestionSchedulingService(
        scheduler=InMemoryScheduler(),
        source_repository=source_repo,
        job_repository=job_repo,
        ingestion_services={SourceType.PUBMED: StubPubMedIngestionService().ingest},
        options=_build_ingestion_options(
            source_lock_repository=source_lock_repository,
        ),
    )

    with pytest.raises(ValueError, match="already running"):
        await service.trigger_ingestion(source.id, force_recover_lock=True)

    assert source.id in source_lock_repository.by_source
    assert source_lock_repository.by_source[source.id].lock_token == "active-lock-token"
    assert source_lock_repository.release_calls == 0


@pytest.mark.asyncio
async def test_run_due_jobs_releases_source_lock_after_completion() -> None:
    schedule = IngestionSchedule(
        enabled=True,
        frequency=ScheduleFrequency.HOURLY,
        start_time=datetime.now(UTC) - timedelta(hours=1),
    )
    source = _build_source(schedule)
    source_repo = StubSourceRepository(source)
    job_repo = StubJobRepository()
    pubmed_service = StubPubMedIngestionService()
    source_lock_repository = StubSourceLockRepository()
    scheduler = InMemoryScheduler()

    service = IngestionSchedulingService(
        scheduler=scheduler,
        source_repository=source_repo,
        job_repository=job_repo,
        ingestion_services={SourceType.PUBMED: pubmed_service.ingest},
        options=_build_ingestion_options(
            source_lock_repository=source_lock_repository,
        ),
    )

    await service.schedule_source(source.id)
    await service.run_due_jobs(as_of=datetime.now(UTC) + timedelta(hours=1, seconds=1))

    assert source.id not in source_lock_repository.by_source
    assert source_lock_repository.release_calls == 1


@pytest.mark.asyncio
async def test_trigger_ingestion_hard_timeout_marks_failed_metadata() -> None:
    schedule = IngestionSchedule(
        enabled=True,
        frequency=ScheduleFrequency.HOURLY,
        start_time=datetime.now(UTC) - timedelta(hours=1),
    )
    source = _build_source(schedule)
    job_repo = StubJobRepository()
    service = IngestionSchedulingService(
        scheduler=InMemoryScheduler(),
        source_repository=StubSourceRepository(source),
        job_repository=job_repo,
        ingestion_services={
            SourceType.PUBMED: SlowTimeoutPubMedIngestionService().ingest,
        },
        options=_build_ingestion_options(
            ingestion_job_hard_timeout_seconds=1,
        ),
    )

    with pytest.raises(TimeoutError):
        await service.trigger_ingestion(source.id)

    failed_jobs = [
        job for job in job_repo.saved if job.status == IngestionStatus.FAILED
    ]
    assert failed_jobs
    failed_job = failed_jobs[-1]
    assert failed_job.errors
    timeout_error = failed_job.errors[-1]
    assert timeout_error.error_type == "timeout"
    assert (
        timeout_error.error_details.get("timeout_scope") == "ingestion_job_hard_timeout"
    )
    failure_metadata = failed_job.metadata.get("failure")
    assert isinstance(failure_metadata, dict)
    assert failure_metadata.get("error_type") == "timeout"
    assert failure_metadata.get("timeout_scope") == "ingestion_job_hard_timeout"


@pytest.mark.asyncio
async def test_run_due_jobs_compacts_stale_ledger_entries() -> None:
    source = _build_source(
        IngestionSchedule(
            enabled=False,
            frequency=ScheduleFrequency.MANUAL,
            start_time=datetime.now(UTC),
        ),
    )
    ledger_repository = StubSourceRecordLedgerRepository(delete_return_value=7)
    service = IngestionSchedulingService(
        scheduler=InMemoryScheduler(),
        source_repository=StubSourceRepository(source),
        job_repository=StubJobRepository(),
        ingestion_services={},
        options=_build_ingestion_options(
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
        options=_build_ingestion_options(),
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
async def test_run_due_jobs_logs_prolonged_deterministic_query_fallback_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    schedule = IngestionSchedule(
        enabled=True,
        frequency=ScheduleFrequency.HOURLY,
        start_time=datetime.now(UTC) - timedelta(hours=1),
    )
    source = _build_source(schedule)
    now = datetime.now(UTC)
    prior_jobs = [
        _build_completed_job(
            source.id,
            triggered_at=now - timedelta(hours=2),
            metadata={"query_generation": {"execution_mode": "deterministic"}},
        ),
        _build_completed_job(
            source.id,
            triggered_at=now - timedelta(hours=1),
            metadata={"query_generation": {"execution_mode": "deterministic"}},
        ),
    ]
    source_repo = StubSourceRepository(source)
    job_repo = StubJobRepository(initial_jobs=prior_jobs)
    scheduler = InMemoryScheduler()
    service = IngestionSchedulingService(
        scheduler=scheduler,
        source_repository=source_repo,
        job_repository=job_repo,
        ingestion_services={
            SourceType.PUBMED: DeterministicFallbackPubMedIngestionService().ingest,
        },
        options=_build_ingestion_options(),
    )

    await service.schedule_source(source.id)
    with caplog.at_level(logging.WARNING):
        await service.run_due_jobs(
            as_of=datetime.now(UTC) + timedelta(hours=1, seconds=1),
        )

    assert any(
        "Prolonged deterministic query fallback detected" in record.message
        for record in caplog.records
    )


@pytest.mark.asyncio
async def test_schedule_source_fails_without_extraction_queue_contract() -> None:
    schedule = IngestionSchedule(
        enabled=True,
        frequency=ScheduleFrequency.HOURLY,
        start_time=datetime.now(UTC) - timedelta(hours=1),
    )
    source = _build_source(schedule)
    service = IngestionSchedulingService(
        scheduler=InMemoryScheduler(),
        source_repository=StubSourceRepository(source),
        job_repository=StubJobRepository(),
        ingestion_services={SourceType.PUBMED: StubPubMedIngestionService().ingest},
    )

    with pytest.raises(ValueError, match="Extraction queue contract is required"):
        await service.schedule_source(source.id)


@pytest.mark.asyncio
async def test_trigger_ingestion_fails_without_source_processor_contract() -> None:
    schedule = IngestionSchedule(
        enabled=True,
        frequency=ScheduleFrequency.HOURLY,
        start_time=datetime.now(UTC) - timedelta(hours=1),
    )
    source = _build_source(schedule)
    queue_service = StubExtractionQueueService()
    runner_service = StubExtractionRunnerService({SourceType.CLINVAR.value})
    service = IngestionSchedulingService(
        scheduler=InMemoryScheduler(),
        source_repository=StubSourceRepository(source),
        job_repository=StubJobRepository(),
        ingestion_services={SourceType.PUBMED: StubPubMedIngestionService().ingest},
        options=_build_ingestion_options(
            extraction_queue_service=queue_service,
            extraction_runner_service=runner_service,
        ),
    )

    with pytest.raises(
        ValueError,
        match="No extraction processor contract registered",
    ):
        await service.trigger_ingestion(source.id)


@pytest.mark.asyncio
async def test_trigger_ingestion_queues_and_runs_extraction_for_pubmed_source() -> None:
    schedule = IngestionSchedule(
        enabled=True,
        frequency=ScheduleFrequency.HOURLY,
        start_time=datetime.now(UTC) - timedelta(hours=1),
    )
    source = _build_source(schedule)
    queue_service = StubExtractionQueueService()
    runner_service = StubExtractionRunnerService({SourceType.PUBMED.value})
    service = IngestionSchedulingService(
        scheduler=InMemoryScheduler(),
        source_repository=StubSourceRepository(source),
        job_repository=StubJobRepository(),
        ingestion_services={
            SourceType.PUBMED: QueueingSourceIngestionService(SourceType.PUBMED).ingest,
        },
        options=_build_ingestion_options(
            extraction_queue_service=queue_service,
            extraction_runner_service=runner_service,
        ),
    )

    await service.trigger_ingestion(source.id)

    assert queue_service.calls
    queued_targets = queue_service.calls[0][2]
    assert queued_targets[0].source_type == SourceType.PUBMED.value
    assert runner_service.calls
    assert runner_service.calls[0][2] == len(queued_targets)


@pytest.mark.asyncio
async def test_trigger_ingestion_marks_job_as_api_triggered() -> None:
    schedule = IngestionSchedule(
        enabled=True,
        frequency=ScheduleFrequency.HOURLY,
        start_time=datetime.now(UTC) - timedelta(hours=1),
    )
    source = _build_source(schedule)
    job_repository = StubJobRepository()
    service = IngestionSchedulingService(
        scheduler=InMemoryScheduler(),
        source_repository=StubSourceRepository(source),
        job_repository=job_repository,
        ingestion_services={SourceType.PUBMED: StubPubMedIngestionService().ingest},
        options=_build_ingestion_options(),
    )

    await service.trigger_ingestion(source.id)

    latest_jobs = job_repository.find_by_source(source.id)
    assert latest_jobs
    latest_job = latest_jobs[0]
    assert latest_job.trigger == IngestionTrigger.API
    assert latest_job.provenance.acquired_by == "ingestion-api"
    assert latest_job.provenance.processing_steps == ("api_triggered_ingestion",)


@pytest.mark.asyncio
async def test_trigger_ingestion_skips_legacy_queue_when_requested() -> None:
    schedule = IngestionSchedule(
        enabled=True,
        frequency=ScheduleFrequency.HOURLY,
        start_time=datetime.now(UTC) - timedelta(hours=1),
    )
    source = _build_source(schedule)
    queue_service = StubExtractionQueueService()
    runner_service = StubExtractionRunnerService({SourceType.PUBMED.value})
    service = IngestionSchedulingService(
        scheduler=InMemoryScheduler(),
        source_repository=StubSourceRepository(source),
        job_repository=StubJobRepository(),
        ingestion_services={
            SourceType.PUBMED: QueueingSourceIngestionService(SourceType.PUBMED).ingest,
        },
        options=_build_ingestion_options(
            extraction_queue_service=queue_service,
            extraction_runner_service=runner_service,
        ),
    )

    await service.trigger_ingestion(
        source.id,
        skip_legacy_extraction_queue=True,
    )

    assert queue_service.calls == []
    assert runner_service.calls == []


@pytest.mark.asyncio
async def test_trigger_ingestion_queues_and_runs_extraction_for_clinvar_source() -> (
    None
):
    schedule = IngestionSchedule(
        enabled=True,
        frequency=ScheduleFrequency.HOURLY,
        start_time=datetime.now(UTC) - timedelta(hours=1),
    )
    source = _build_source(schedule).model_copy(
        update={"source_type": SourceType.CLINVAR},
    )
    queue_service = StubExtractionQueueService()
    runner_service = StubExtractionRunnerService({SourceType.CLINVAR.value})
    service = IngestionSchedulingService(
        scheduler=InMemoryScheduler(),
        source_repository=StubSourceRepository(source),
        job_repository=StubJobRepository(),
        ingestion_services={
            SourceType.CLINVAR: QueueingSourceIngestionService(
                SourceType.CLINVAR,
            ).ingest,
        },
        options=_build_ingestion_options(
            extraction_queue_service=queue_service,
            extraction_runner_service=runner_service,
        ),
    )

    await service.trigger_ingestion(source.id)

    assert queue_service.calls
    queued_targets = queue_service.calls[0][2]
    assert queued_targets[0].source_type == SourceType.CLINVAR.value
    assert runner_service.calls
    assert runner_service.calls[0][2] == len(queued_targets)


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
        options=_build_ingestion_options(
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


@pytest.mark.asyncio
async def test_trigger_ingestion_provides_pipeline_progress_context() -> None:
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
    progress_updates: list[IngestionProgressUpdate] = []

    service = IngestionSchedulingService(
        scheduler=scheduler,
        source_repository=source_repo,
        job_repository=job_repo,
        ingestion_services={SourceType.PUBMED: pubmed_service.ingest},
        options=_build_ingestion_options(),
    )

    await service.trigger_ingestion(
        source.id,
        pipeline_run_id="pipeline-run-ctx-001",
        progress_callback=progress_updates.append,
    )

    assert pubmed_service.contexts
    context = pubmed_service.contexts[0]
    assert context.pipeline_run_id == "pipeline-run-ctx-001"
    assert context.progress_callback is not None
    assert progress_updates
    assert progress_updates[0].event_type == "ingestion_job_started"
    assert progress_updates[0].ingestion_job_id == context.ingestion_job_id
