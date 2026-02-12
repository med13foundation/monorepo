"""Application service coordinating scheduled ingestion across sources."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Awaitable, Callable, Mapping  # noqa: UP035
from uuid import UUID, uuid4

from src.application.services.pubmed_discovery_service import (
    PUBMED_STORAGE_METADATA_ARTICLE_ID_KEY,
    PUBMED_STORAGE_METADATA_JOB_ID_KEY,
    PUBMED_STORAGE_METADATA_OWNER_ID_KEY,
    PUBMED_STORAGE_METADATA_RETRYABLE_KEY,
    PUBMED_STORAGE_METADATA_USE_CASE_KEY,
    PubMedDiscoveryService,
    PubmedDownloadRequest,
)
from src.domain.entities import ingestion_job, user_data_source
from src.domain.services.storage_providers import StorageOperationError
from src.domain.value_objects.provenance import DataSource as ProvenanceSource
from src.domain.value_objects.provenance import Provenance
from src.type_definitions.storage import StorageOperationRecord, StorageUseCase

if TYPE_CHECKING:
    from src.application.services import (
        ExtractionQueueService,
        ExtractionRunnerService,
    )
    from src.application.services.ports.scheduler_port import (
        ScheduledJob,
        SchedulerPort,
    )
    from src.domain.repositories import (
        ingestion_job_repository,
        storage_repository,
        user_data_source_repository,
    )
    from src.domain.services.pubmed_ingestion import PubMedIngestionSummary
    from src.type_definitions.common import JSONObject


@dataclass(frozen=True)
class IngestionSchedulingOptions:
    storage_operation_repository: (
        storage_repository.StorageOperationRepository | None
    ) = None
    pubmed_discovery_service: PubMedDiscoveryService | None = None
    extraction_queue_service: ExtractionQueueService | None = None
    extraction_runner_service: ExtractionRunnerService | None = None
    retry_batch_size: int = 25


logger = logging.getLogger(__name__)


class IngestionSchedulingService:
    """Coordinates scheduler registration and execution of ingestion jobs."""

    def __init__(
        self,
        scheduler: SchedulerPort,
        source_repository: user_data_source_repository.UserDataSourceRepository,
        job_repository: ingestion_job_repository.IngestionJobRepository,
        ingestion_services: Mapping[
            user_data_source.SourceType,
            Callable[
                [user_data_source.UserDataSource],
                Awaitable[PubMedIngestionSummary],
            ],
        ],
        options: IngestionSchedulingOptions | None = None,
    ) -> None:
        resolved_options = options or IngestionSchedulingOptions()
        self._scheduler = scheduler
        self._source_repository = source_repository
        self._job_repository = job_repository
        self._ingestion_services = dict(ingestion_services)
        self._storage_operation_repository = (
            resolved_options.storage_operation_repository
        )
        self._pubmed_discovery_service = resolved_options.pubmed_discovery_service
        self._extraction_queue_service = resolved_options.extraction_queue_service
        self._extraction_runner_service = resolved_options.extraction_runner_service
        self._retry_batch_size = max(resolved_options.retry_batch_size, 1)

    async def schedule_source(self, source_id: UUID) -> ScheduledJob:
        """Register a source with the scheduler backend."""
        source = self._get_source(source_id)
        schedule = source.ingestion_schedule
        if not schedule.requires_scheduler:
            msg = "Source schedule must be enabled with non-manual frequency"
            raise ValueError(msg)

        scheduled = self._scheduler.register_job(source_id, schedule)
        updated_schedule = schedule.model_copy(
            update={
                "backend_job_id": scheduled.job_id,
                "next_run_at": scheduled.next_run_at,
            },
        )
        self._source_repository.update_ingestion_schedule(source_id, updated_schedule)
        return scheduled

    def unschedule_source(self, source_id: UUID) -> None:
        """Remove a scheduled job for the given source if present."""
        source = self._get_source(source_id)
        job_id = source.ingestion_schedule.backend_job_id
        if job_id:
            self._scheduler.remove_job(job_id)
            updated = source.ingestion_schedule.model_copy(
                update={"backend_job_id": None, "next_run_at": None},
            )
            self._source_repository.update_ingestion_schedule(source_id, updated)

    async def run_due_jobs(self, *, as_of: datetime | None = None) -> None:
        """Execute all jobs that are due as of the provided timestamp."""
        due_jobs = self._scheduler.get_due_jobs(as_of=as_of)
        for job in due_jobs:
            await self._execute_job(job)
        await self._retry_failed_pdf_downloads()

    async def trigger_ingestion(
        self,
        source_id: UUID,
    ) -> PubMedIngestionSummary:
        """Manually trigger ingestion for a source outside of scheduler cadence."""
        source = self._get_source(source_id)
        if source.status != user_data_source.SourceStatus.ACTIVE:
            msg = "Source must be active before ingestion can run"
            raise ValueError(msg)
        if not source.ingestion_schedule.requires_scheduler:
            msg = "Source must have an enabled non-manual ingestion schedule"
            raise ValueError(msg)
        return await self._run_ingestion_for_source(source)

    async def _execute_job(self, scheduled_job: ScheduledJob) -> None:
        source = self._get_source(scheduled_job.source_id)
        if source.status != user_data_source.SourceStatus.ACTIVE:
            return
        if (
            source.ingestion_schedule.frequency
            == user_data_source.ScheduleFrequency.MANUAL
        ):
            return
        await self._run_ingestion_for_source(source)

    async def _run_ingestion_for_source(
        self,
        source: user_data_source.UserDataSource,
    ) -> PubMedIngestionSummary:
        service = self._ingestion_services.get(source.source_type)
        if service is None:
            msg = f"No ingestion service registered for {source.source_type}"
            raise ValueError(msg)

        job = self._job_repository.save(self._create_ingestion_job(source))
        running = self._job_repository.save(job.start_execution())
        try:
            summary = await service(source)
            metrics = ingestion_job.JobMetrics(
                records_processed=summary.created_publications
                + summary.updated_publications,
                records_failed=0,
                records_skipped=0,
                bytes_processed=0,
                api_calls_made=0,
                duration_seconds=None,
                records_per_second=None,
            )
            # Record executed query in metadata if available
            metadata = dict(running.metadata or {})
            if hasattr(summary, "executed_query") and summary.executed_query:
                metadata["executed_query"] = summary.executed_query

            extraction_metadata = self._enqueue_extraction(
                source=source,
                ingestion_job_id=running.id,
                summary=summary,
            )
            if extraction_metadata:
                metadata["extraction_queue"] = extraction_metadata
                extraction_run = await self._run_extraction(
                    source=source,
                    ingestion_job_id=running.id,
                    queued_count=extraction_metadata["queued"],
                )
                if extraction_run:
                    metadata["extraction_run"] = extraction_run

            completed = running.model_copy(
                update={"metadata": metadata},
            ).complete_successfully(metrics)
        except Exception as exc:  # pragma: no cover - defensive
            error = ingestion_job.IngestionError(
                error_type="scheduler_failure",
                error_message=str(exc),
                record_id=None,
            )
            failed = running.fail(error)
            self._job_repository.save(failed)
            raise
        else:
            self._job_repository.save(completed)
            updated_source = (
                self._source_repository.record_ingestion(source.id) or source
            )
            self._update_schedule_after_run(updated_source)
            return summary

    def _enqueue_extraction(
        self,
        *,
        source: user_data_source.UserDataSource,
        ingestion_job_id: UUID,
        summary: PubMedIngestionSummary,
    ) -> dict[str, int] | None:
        if self._extraction_queue_service is None:
            return None

        combined_ids = list(summary.created_publication_ids) + list(
            summary.updated_publication_ids,
        )
        publication_ids = list(dict.fromkeys(combined_ids))
        if not publication_ids:
            return None

        enqueue_summary = self._extraction_queue_service.enqueue_for_ingestion(
            source_id=source.id,
            ingestion_job_id=ingestion_job_id,
            publication_ids=publication_ids,
        )
        return {
            "requested": enqueue_summary.requested,
            "queued": enqueue_summary.queued,
            "skipped": enqueue_summary.skipped,
            "version": enqueue_summary.extraction_version,
        }

    async def _run_extraction(
        self,
        *,
        source: user_data_source.UserDataSource,
        ingestion_job_id: UUID,
        queued_count: int,
    ) -> JSONObject | None:
        if self._extraction_runner_service is None:
            return None
        if queued_count <= 0:
            return None
        summary = await self._extraction_runner_service.run_for_ingestion_job(
            source_id=source.id,
            ingestion_job_id=ingestion_job_id,
            expected_items=queued_count,
        )
        return summary.to_metadata()

    def _create_ingestion_job(
        self,
        source: user_data_source.UserDataSource,
    ) -> ingestion_job.IngestionJob:
        return ingestion_job.IngestionJob(
            id=uuid4(),
            source_id=source.id,
            trigger=ingestion_job.IngestionTrigger.SCHEDULED,
            triggered_by=None,
            started_at=None,
            completed_at=None,
            provenance=Provenance(
                source=ProvenanceSource.COMPUTED,
                source_version=None,
                source_url=None,
                acquired_by="ingestion-scheduler",
                processing_steps=("scheduled_ingestion",),
                quality_score=None,
            ),
            metadata={},
            source_config_snapshot=source.configuration.model_dump(),
        )

    def _get_source(self, source_id: UUID) -> user_data_source.UserDataSource:
        source = self._source_repository.find_by_id(source_id)
        if source is None:
            msg = f"Data source {source_id} not found"
            raise ValueError(msg)
        return source

    def _update_schedule_after_run(
        self,
        source: user_data_source.UserDataSource,
    ) -> None:
        schedule = source.ingestion_schedule
        updates: dict[str, datetime | None] = {"last_run_at": datetime.now(UTC)}
        job_id = schedule.backend_job_id
        if job_id:
            job = self._scheduler.get_job(job_id)
            if job:
                updates["next_run_at"] = job.next_run_at
        updated_schedule = schedule.model_copy(update=updates)
        self._source_repository.update_ingestion_schedule(source.id, updated_schedule)

    async def _retry_failed_pdf_downloads(self) -> None:
        """Retry failed PDF storage operations for PubMed discovery jobs."""
        if (
            self._storage_operation_repository is None
            or self._pubmed_discovery_service is None
        ):
            return

        operations = self._storage_operation_repository.list_failed_store_operations(
            limit=self._retry_batch_size,
        )
        for operation in operations:
            context = self._build_pdf_retry_context(operation)
            if context is None:
                continue
            job = self._pubmed_discovery_service.get_search_job(
                context.owner_id,
                context.job_id,
            )
            if job is None:
                self._mark_operation_retry_disabled(operation)
                continue

            if self._article_already_stored(job.result_metadata, context.article_id):
                self._mark_operation_retry_disabled(operation)
                continue

            try:
                await self._pubmed_discovery_service.download_article_pdf(
                    context.owner_id,
                    PubmedDownloadRequest(
                        job_id=context.job_id,
                        article_id=context.article_id,
                    ),
                )
            except (
                RuntimeError,
                ValueError,
                StorageOperationError,
            ) as exc:  # pragma: no cover - defensive logging upstream
                logger.warning(
                    "PubMed PDF retry failed",
                    extra={
                        "job_id": str(context.job_id),
                        "article_id": context.article_id,
                        "error": str(exc),
                    },
                )
                continue
            else:
                self._mark_operation_retry_disabled(operation)

    @staticmethod
    def _article_already_stored(
        metadata: Mapping[str, object],
        article_id: str,
    ) -> bool:
        stored_assets = metadata.get("stored_assets")
        if not isinstance(stored_assets, dict):
            return False
        normalized_id = str(article_id)
        stored_keys = {str(key) for key in stored_assets}
        return normalized_id in stored_keys

    def _build_pdf_retry_context(
        self,
        operation: StorageOperationRecord,
    ) -> _PdfRetryContext | None:
        metadata = operation.metadata or {}
        use_case = metadata.get(PUBMED_STORAGE_METADATA_USE_CASE_KEY)
        retryable = metadata.get(PUBMED_STORAGE_METADATA_RETRYABLE_KEY, True)
        if use_case != StorageUseCase.PDF.value or not bool(retryable):
            return None
        job_id_raw = metadata.get(PUBMED_STORAGE_METADATA_JOB_ID_KEY)
        owner_id_raw = metadata.get(PUBMED_STORAGE_METADATA_OWNER_ID_KEY)
        article_id_raw = metadata.get(PUBMED_STORAGE_METADATA_ARTICLE_ID_KEY)
        if not job_id_raw or not owner_id_raw or not article_id_raw:
            return None
        try:
            return _PdfRetryContext(
                operation_id=operation.id,
                job_id=UUID(str(job_id_raw)),
                owner_id=UUID(str(owner_id_raw)),
                article_id=str(article_id_raw),
            )
        except ValueError:
            return None

    def _mark_operation_retry_disabled(
        self,
        operation: StorageOperationRecord,
    ) -> None:
        if self._storage_operation_repository is None:
            return
        metadata = (
            dict(operation.metadata) if isinstance(operation.metadata, dict) else {}
        )
        metadata[PUBMED_STORAGE_METADATA_RETRYABLE_KEY] = False
        metadata["retry_completed_at"] = datetime.now(UTC).isoformat()
        self._storage_operation_repository.update_operation_metadata(
            operation.id,
            metadata,
        )


@dataclass(frozen=True)
class _PdfRetryContext:
    operation_id: UUID
    job_id: UUID
    owner_id: UUID
    article_id: str
