"""Application service coordinating scheduled ingestion across sources."""

from __future__ import annotations

import hashlib
import inspect
import json
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
from src.domain.entities.source_sync_state import CheckpointKind, SourceSyncState
from src.domain.services.ingestion import IngestionRunContext
from src.domain.services.storage_providers import StorageOperationError
from src.domain.value_objects.provenance import DataSource as ProvenanceSource
from src.domain.value_objects.provenance import Provenance
from src.type_definitions import data_sources as data_source_types
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
    from src.domain.repositories import (
        source_record_ledger_repository as source_record_ledger_repo,
    )
    from src.domain.repositories import (
        source_sync_state_repository as source_sync_state_repo,
    )
    from src.domain.services.ingestion import IngestionRunSummary
    from src.type_definitions.common import JSONValue


@dataclass(frozen=True)
class IngestionSchedulingOptions:
    storage_operation_repository: (
        storage_repository.StorageOperationRepository | None
    ) = None
    pubmed_discovery_service: PubMedDiscoveryService | None = None
    extraction_queue_service: ExtractionQueueService | None = None
    extraction_runner_service: ExtractionRunnerService | None = None
    source_sync_state_repository: (
        source_sync_state_repo.SourceSyncStateRepository | None
    ) = None
    source_record_ledger_repository: (
        source_record_ledger_repo.SourceRecordLedgerRepository | None
    ) = None
    retry_batch_size: int = 25


logger = logging.getLogger(__name__)
MIN_POSITIONAL_PARAMETERS_WITH_CONTEXT = 2


class IngestionSchedulingService:
    """Coordinates scheduler registration and execution of ingestion jobs."""

    def __init__(
        self,
        scheduler: SchedulerPort,
        source_repository: user_data_source_repository.UserDataSourceRepository,
        job_repository: ingestion_job_repository.IngestionJobRepository,
        ingestion_services: Mapping[
            user_data_source.SourceType,
            Callable[..., Awaitable[IngestionRunSummary]],
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
        self._source_sync_state_repository = (
            resolved_options.source_sync_state_repository
        )
        self._source_record_ledger_repository = (
            resolved_options.source_record_ledger_repository
        )
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
    ) -> IngestionRunSummary:
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
    ) -> IngestionRunSummary:
        service = self._get_ingestion_service(source)

        job = self._job_repository.save(self._create_ingestion_job(source))
        running = self._job_repository.save(job.start_execution())
        sync_state_before = self._prepare_sync_state_for_attempt(source)
        run_context = self._build_run_context(
            source=source,
            ingestion_job_id=running.id,
            sync_state=sync_state_before,
        )
        try:
            summary = await self._invoke_ingestion_service(
                service=service,
                source=source,
                context=run_context,
            )
            sync_state_after = self._persist_sync_state_on_success(
                sync_state=sync_state_before,
                ingestion_job_id=running.id,
                summary=summary,
            )
            skipped_records = self._int_summary_field(summary, "skipped_records") + (
                self._int_summary_field(summary, "unchanged_records")
            )
            metrics = ingestion_job.JobMetrics(
                records_processed=summary.created_publications
                + summary.updated_publications,
                records_failed=0,
                records_skipped=skipped_records,
                bytes_processed=0,
                api_calls_made=0,
                duration_seconds=None,
                records_per_second=None,
            )
            metadata = self._build_source_metadata(
                running=running,
                summary=summary,
                sync_state_before=sync_state_before,
                sync_state_after=sync_state_after,
            )

            extraction_metadata = self._enqueue_extraction(
                source=source,
                ingestion_job_id=running.id,
                summary=summary,
            )
            if extraction_metadata:
                metadata = metadata.model_copy(
                    update={"extraction_queue": extraction_metadata},
                )
                extraction_run = await self._run_extraction(
                    source=source,
                    ingestion_job_id=running.id,
                    queued_count=extraction_metadata.queued,
                )
                if extraction_run:
                    metadata = metadata.model_copy(
                        update={"extraction_run": extraction_run},
                    )

            completed = running.model_copy(
                update={"metadata": metadata.to_json_object()},
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

    def _get_ingestion_service(
        self,
        source: user_data_source.UserDataSource,
    ) -> Callable[..., Awaitable[IngestionRunSummary]]:
        """Return the ingestion service for a source type."""
        service = self._ingestion_services.get(source.source_type)
        if service is None:
            msg = f"No ingestion service registered for {source.source_type}"
            raise ValueError(msg)
        return service

    def _build_source_metadata(
        self,
        *,
        running: ingestion_job.IngestionJob,
        summary: IngestionRunSummary,
        sync_state_before: SourceSyncState | None,
        sync_state_after: SourceSyncState | None,
    ) -> data_source_types.IngestionJobMetadata:
        """Build ingestion-job metadata including query-generation trace details."""
        metadata = (
            data_source_types.IngestionJobMetadata.parse_optional(running.metadata)
            or data_source_types.IngestionJobMetadata()
        )
        executed_query = getattr(summary, "executed_query", None)
        if executed_query and isinstance(executed_query, str):
            metadata = metadata.model_copy(update={"executed_query": executed_query})

        query_generation_metadata = self._build_query_generation_metadata(summary)
        if query_generation_metadata is not None:
            metadata = metadata.model_copy(
                update={"query_generation": query_generation_metadata},
            )

        idempotency_metadata = self._build_idempotency_metadata(
            summary=summary,
            sync_state_before=sync_state_before,
            sync_state_after=sync_state_after,
        )
        if idempotency_metadata is not None:
            metadata = metadata.model_copy(update={"idempotency": idempotency_metadata})
        return metadata

    @staticmethod
    def _build_query_generation_metadata(
        summary: IngestionRunSummary,
    ) -> data_source_types.IngestionQueryGenerationMetadata | None:
        """Build the optional query-generation metadata payload."""
        run_id = getattr(summary, "query_generation_run_id", None)
        model = getattr(summary, "query_generation_model", None)
        decision = getattr(summary, "query_generation_decision", None)
        confidence = getattr(summary, "query_generation_confidence", None)

        has_signal = any(
            value is not None
            for value in (
                run_id,
                model,
                decision,
                confidence,
            )
        )
        if not has_signal:
            return None
        return data_source_types.IngestionQueryGenerationMetadata(
            run_id=run_id if isinstance(run_id, str) else None,
            model=model if isinstance(model, str) else None,
            decision=decision if isinstance(decision, str) else None,
            confidence=confidence if isinstance(confidence, float | int) else None,
        )

    def _prepare_sync_state_for_attempt(
        self,
        source: user_data_source.UserDataSource,
    ) -> SourceSyncState | None:
        repository = self._source_sync_state_repository
        if repository is None:
            return None

        query_signature = self._build_query_signature(source)
        default_checkpoint_kind = self._default_checkpoint_kind(source.source_type)
        existing = repository.get_by_source(source.id)
        if existing is None:
            existing = SourceSyncState(
                source_id=source.id,
                source_type=source.source_type,
                checkpoint_kind=default_checkpoint_kind,
                query_signature=query_signature,
            )
        elif (
            existing.checkpoint_kind == CheckpointKind.NONE
            and default_checkpoint_kind != CheckpointKind.NONE
        ):
            existing = existing.model_copy(
                update={"checkpoint_kind": default_checkpoint_kind},
            )
        if (
            existing.query_signature is not None
            and existing.query_signature != query_signature
        ):
            existing = existing.model_copy(
                update={
                    "checkpoint_payload": {},
                    "checkpoint_kind": default_checkpoint_kind,
                },
            )
        attempted = existing.mark_attempt().model_copy(
            update={"query_signature": query_signature},
        )
        return repository.upsert(attempted)

    def _build_run_context(
        self,
        *,
        source: user_data_source.UserDataSource,
        ingestion_job_id: UUID,
        sync_state: SourceSyncState | None,
    ) -> IngestionRunContext | None:
        if (
            self._source_sync_state_repository is None
            and self._source_record_ledger_repository is None
        ):
            return None

        resolved_state = sync_state or SourceSyncState(
            source_id=source.id,
            source_type=source.source_type,
            query_signature=self._build_query_signature(source),
        )
        query_signature = resolved_state.query_signature or self._build_query_signature(
            source,
        )
        return IngestionRunContext(
            ingestion_job_id=ingestion_job_id,
            source_sync_state=resolved_state,
            query_signature=query_signature,
            source_record_ledger_repository=self._source_record_ledger_repository,
        )

    async def _invoke_ingestion_service(
        self,
        *,
        service: Callable[..., Awaitable[IngestionRunSummary]],
        source: user_data_source.UserDataSource,
        context: IngestionRunContext | None,
    ) -> IngestionRunSummary:
        if context is not None and self._service_accepts_context(service):
            return await service(source, context=context)
        return await service(source)

    @staticmethod
    def _service_accepts_context(
        service: Callable[..., Awaitable[IngestionRunSummary]],
    ) -> bool:
        try:
            signature = inspect.signature(service)
        except (TypeError, ValueError):
            return False
        parameters = signature.parameters
        if "context" in parameters:
            return True
        positional_count = sum(
            1
            for parameter in parameters.values()
            if parameter.kind
            in (
                inspect.Parameter.POSITIONAL_ONLY,
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
            )
        )
        return positional_count >= MIN_POSITIONAL_PARAMETERS_WITH_CONTEXT

    def _persist_sync_state_on_success(
        self,
        *,
        sync_state: SourceSyncState | None,
        ingestion_job_id: UUID,
        summary: IngestionRunSummary,
    ) -> SourceSyncState | None:
        repository = self._source_sync_state_repository
        if repository is None or sync_state is None:
            return None

        checkpoint_after_raw = getattr(summary, "checkpoint_after", None)
        if isinstance(checkpoint_after_raw, dict):
            checkpoint_after: dict[str, JSONValue] = dict(checkpoint_after_raw)
        else:
            checkpoint_after = dict(sync_state.checkpoint_payload)

        updated = sync_state.mark_success(
            successful_job_id=ingestion_job_id,
            checkpoint_payload=checkpoint_after,
        )
        checkpoint_kind = self._resolve_checkpoint_kind(
            raw_value=getattr(summary, "checkpoint_kind", None),
            fallback=sync_state.checkpoint_kind,
        )
        query_signature = getattr(summary, "query_signature", None)
        update_payload: dict[str, object] = {"checkpoint_kind": checkpoint_kind}
        if isinstance(query_signature, str) and query_signature.strip():
            update_payload["query_signature"] = query_signature
        updated = updated.model_copy(update=update_payload)
        return repository.upsert(updated)

    @staticmethod
    def _int_summary_field(
        summary: IngestionRunSummary,
        field_name: str,
    ) -> int:
        raw_value = getattr(summary, field_name, 0)
        return raw_value if isinstance(raw_value, int) else 0

    def _build_idempotency_metadata(
        self,
        *,
        summary: IngestionRunSummary,
        sync_state_before: SourceSyncState | None,
        sync_state_after: SourceSyncState | None,
    ) -> data_source_types.IngestionIdempotencyMetadata | None:
        query_signature = getattr(summary, "query_signature", None)
        if not isinstance(query_signature, str) or not query_signature.strip():
            query_signature = (
                sync_state_after.query_signature
                if sync_state_after is not None
                else (
                    sync_state_before.query_signature
                    if sync_state_before is not None
                    else None
                )
            )
        resolved_query_signature = (
            query_signature
            if isinstance(query_signature, str) and query_signature.strip()
            else None
        )
        resolved_checkpoint_kind = self._resolve_checkpoint_kind(
            raw_value=getattr(summary, "checkpoint_kind", None),
            fallback=(
                sync_state_after.checkpoint_kind
                if sync_state_after is not None
                else (
                    sync_state_before.checkpoint_kind
                    if sync_state_before is not None
                    else CheckpointKind.NONE
                )
            ),
        )

        checkpoint_before_raw = getattr(summary, "checkpoint_before", None)
        if isinstance(checkpoint_before_raw, dict):
            checkpoint_before: dict[str, JSONValue] | None = dict(checkpoint_before_raw)
        elif sync_state_before is not None:
            checkpoint_before = dict(sync_state_before.checkpoint_payload)
        else:
            checkpoint_before = None

        checkpoint_after_raw = getattr(summary, "checkpoint_after", None)
        if isinstance(checkpoint_after_raw, dict):
            checkpoint_after: dict[str, JSONValue] | None = dict(checkpoint_after_raw)
        elif sync_state_after is not None:
            checkpoint_after = dict(sync_state_after.checkpoint_payload)
        else:
            checkpoint_after = None

        new_records = self._int_summary_field(summary, "new_records")
        updated_records = self._int_summary_field(summary, "updated_records")
        unchanged_records = self._int_summary_field(summary, "unchanged_records")
        skipped_records = self._int_summary_field(summary, "skipped_records")

        has_signal = (
            resolved_query_signature is not None
            or resolved_checkpoint_kind != CheckpointKind.NONE
            or checkpoint_before is not None
            or checkpoint_after is not None
            or new_records > 0
            or updated_records > 0
            or unchanged_records > 0
            or skipped_records > 0
        )
        if not has_signal:
            return None

        return data_source_types.IngestionIdempotencyMetadata(
            query_signature=resolved_query_signature,
            checkpoint_kind=resolved_checkpoint_kind.value,
            checkpoint_before=checkpoint_before,
            checkpoint_after=checkpoint_after,
            new_records=new_records,
            updated_records=updated_records,
            unchanged_records=unchanged_records,
            skipped_records=skipped_records,
        )

    @staticmethod
    def _resolve_checkpoint_kind(
        *,
        raw_value: object,
        fallback: CheckpointKind,
    ) -> CheckpointKind:
        if isinstance(raw_value, CheckpointKind):
            return raw_value
        if isinstance(raw_value, str):
            normalized = raw_value.strip().lower()
            for kind in CheckpointKind:
                if kind.value == normalized:
                    return kind
        return fallback

    @staticmethod
    def _default_checkpoint_kind(
        source_type: user_data_source.SourceType,
    ) -> CheckpointKind:
        if source_type in (
            user_data_source.SourceType.PUBMED,
            user_data_source.SourceType.CLINVAR,
        ):
            return CheckpointKind.CURSOR
        return CheckpointKind.NONE

    @staticmethod
    def _build_query_signature(source: user_data_source.UserDataSource) -> str:
        canonical_payload = json.dumps(
            {
                "source_type": source.source_type.value,
                "configuration": source.configuration.model_dump(mode="json"),
            },
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        return hashlib.sha256(canonical_payload.encode("utf-8")).hexdigest()

    def _enqueue_extraction(
        self,
        *,
        source: user_data_source.UserDataSource,
        ingestion_job_id: UUID,
        summary: IngestionRunSummary,
    ) -> data_source_types.IngestionExtractionQueueMetadata | None:
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
        return data_source_types.IngestionExtractionQueueMetadata(
            requested=enqueue_summary.requested,
            queued=enqueue_summary.queued,
            skipped=enqueue_summary.skipped,
            version=enqueue_summary.extraction_version,
        )

    async def _run_extraction(
        self,
        *,
        source: user_data_source.UserDataSource,
        ingestion_job_id: UUID,
        queued_count: int,
    ) -> data_source_types.IngestionExtractionRunMetadata | None:
        if self._extraction_runner_service is None:
            return None
        if queued_count <= 0:
            return None
        summary = await self._extraction_runner_service.run_for_ingestion_job(
            source_id=source.id,
            ingestion_job_id=ingestion_job_id,
            expected_items=queued_count,
        )
        return data_source_types.IngestionExtractionRunMetadata(
            source_id=str(summary.source_id) if summary.source_id is not None else None,
            ingestion_job_id=(
                str(summary.ingestion_job_id)
                if summary.ingestion_job_id is not None
                else None
            ),
            requested=summary.requested,
            processed=summary.processed,
            completed=summary.completed,
            skipped=summary.skipped,
            failed=summary.failed,
            started_at=summary.started_at,
            completed_at=summary.completed_at,
        )

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
