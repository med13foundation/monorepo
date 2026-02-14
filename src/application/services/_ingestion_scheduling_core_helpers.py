"""Core scheduling helpers for ingestion execution and metadata orchestration."""

# mypy: disable-error-code="misc"

from __future__ import annotations

import hashlib
import inspect
import json
import logging
from typing import TYPE_CHECKING

from src.domain.entities import ingestion_job, user_data_source
from src.domain.entities.source_sync_state import CheckpointKind, SourceSyncState
from src.domain.services.ingestion import IngestionRunContext, IngestionRunSummary

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable
    from uuid import UUID

    from src.application.services.ingestion_scheduling_service import (
        IngestionSchedulingService,
    )
    from src.application.services.ports.scheduler_port import ScheduledJob

logger = logging.getLogger(__name__)

MIN_POSITIONAL_PARAMETERS_WITH_CONTEXT = 2
DEDUP_WARNING_THRESHOLD = 0.9


class _IngestionSchedulingCoreHelpers:
    """Helpers for orchestrating ingestion execution and summary metadata."""

    async def _execute_job(
        self: IngestionSchedulingService,
        scheduled_job: ScheduledJob,
    ) -> None:
        source = self._get_source(scheduled_job.source_id)
        if source.status != user_data_source.SourceStatus.ACTIVE:
            return
        if (
            source.ingestion_schedule.frequency
            == user_data_source.ScheduleFrequency.MANUAL
        ):
            return
        if self._source_has_running_job(source.id):
            logger.info(
                "Skipping scheduled ingestion because source already has a running job",
                extra={"source_id": str(source.id)},
            )
            return
        await self._run_ingestion_for_source(source)

    async def _run_ingestion_for_source(
        self: IngestionSchedulingService,
        source: user_data_source.UserDataSource,
    ) -> IngestionRunSummary:
        self._ensure_source_not_running(source.id)
        self._assert_extraction_contract(source)
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
            self._emit_dedup_telemetry(source_id=source.id, summary=summary)
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
        except Exception as exc:
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

    def _source_has_running_job(
        self: IngestionSchedulingService,
        source_id: UUID,
    ) -> bool:
        recent_jobs = self._job_repository.find_by_source(source_id, limit=10)
        return any(
            job.status == ingestion_job.IngestionStatus.RUNNING for job in recent_jobs
        )

    def _ensure_source_not_running(
        self: IngestionSchedulingService,
        source_id: UUID,
    ) -> None:
        if self._source_has_running_job(source_id):
            msg = f"Ingestion already running for source {source_id}"
            raise ValueError(msg)

    def _get_ingestion_service(
        self: IngestionSchedulingService,
        source: user_data_source.UserDataSource,
    ) -> Callable[..., Awaitable[IngestionRunSummary]]:
        service = self._ingestion_services.get(source.source_type)
        if service is None:
            msg = f"No ingestion service registered for {source.source_type}"
            raise ValueError(msg)
        return service

    def _assert_extraction_contract(
        self: IngestionSchedulingService,
        source: user_data_source.UserDataSource,
    ) -> None:
        if self._extraction_queue_service is None:
            msg = (
                "Extraction queue contract is required for all datasource ingestions "
                f"(missing for source type {source.source_type.value})"
            )
            raise ValueError(msg)
        runner = self._extraction_runner_service
        if runner is None:
            msg = (
                "Extraction processor contract is required for all datasource "
                f"ingestions (missing runner for source type {source.source_type.value})"
            )
            raise ValueError(msg)
        if not runner.has_processor_for_source_type(source.source_type.value):
            msg = (
                "No extraction processor contract registered for source type "
                f"{source.source_type.value}"
            )
            raise ValueError(msg)

    def _prepare_sync_state_for_attempt(
        self: IngestionSchedulingService,
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
            logger.warning(
                "Source query signature changed; resetting checkpoint payload",
                extra={
                    "source_id": str(source.id),
                    "source_type": source.source_type.value,
                    "previous_signature": existing.query_signature,
                    "new_signature": query_signature,
                },
            )
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
        self: IngestionSchedulingService,
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
        self: IngestionSchedulingService,
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
        self: IngestionSchedulingService,
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
            checkpoint_after = dict(checkpoint_after_raw)
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

    def _emit_dedup_telemetry(
        self: IngestionSchedulingService,
        *,
        source_id: UUID,
        summary: IngestionRunSummary,
    ) -> None:
        fetched_records = summary.fetched_records
        if fetched_records <= 0:
            return
        unchanged_records = self._int_summary_field(summary, "unchanged_records")
        new_records = self._int_summary_field(summary, "new_records")
        updated_records = self._int_summary_field(summary, "updated_records")
        dedup_ratio = unchanged_records / fetched_records
        log_extra = {
            "source_id": str(source_id),
            "fetched_records": fetched_records,
            "new_records": new_records,
            "updated_records": updated_records,
            "unchanged_records": unchanged_records,
            "dedup_ratio": round(dedup_ratio, 4),
        }
        if dedup_ratio >= DEDUP_WARNING_THRESHOLD:
            logger.warning(
                "High dedup ratio detected for source ingestion run",
                extra=log_extra,
            )
            return
        logger.info("Source ingestion dedup telemetry", extra=log_extra)

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
    def _build_query_signature(
        source: user_data_source.UserDataSource,
    ) -> str:
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
