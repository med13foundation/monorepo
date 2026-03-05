"""Core scheduling helpers for ingestion execution and metadata orchestration."""

# mypy: disable-error-code="misc"

from __future__ import annotations

import asyncio
import inspect
import logging
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from uuid import uuid4

from src.domain.entities import ingestion_job, user_data_source

from ._ingestion_scheduling_observability_helpers import (
    _IngestionSchedulingObservabilityHelpers,
)
from ._ingestion_scheduling_shared_helpers import (
    normalize_datetime,
    with_failure_metadata,
)
from ._ingestion_scheduling_state_helpers import _IngestionSchedulingStateHelpers

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable
    from uuid import UUID

    from src.application.services.ingestion_scheduling_service import (
        IngestionSchedulingService,
    )
    from src.application.services.ports.scheduler_port import ScheduledJob
    from src.domain.services.ingestion import IngestionRunContext, IngestionRunSummary
    from src.type_definitions.common import JSONObject

logger = logging.getLogger(__name__)

MIN_POSITIONAL_PARAMETERS_WITH_CONTEXT = 2
ALREADY_RUNNING_ERROR_FRAGMENT = "already running"


class _IngestionSchedulingCoreHelpers(
    _IngestionSchedulingObservabilityHelpers,
    _IngestionSchedulingStateHelpers,
):
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
        try:
            await self._run_ingestion_for_source(
                source,
                trigger=ingestion_job.IngestionTrigger.SCHEDULED,
            )
        except ValueError as exc:
            if ALREADY_RUNNING_ERROR_FRAGMENT in str(exc).lower():
                logger.info(
                    "Skipping scheduled ingestion because source lock is held",
                    extra={"source_id": str(source.id)},
                )
                return
            raise

    async def _run_ingestion_for_source(
        self: IngestionSchedulingService,
        source: user_data_source.UserDataSource,
        *,
        trigger: ingestion_job.IngestionTrigger = ingestion_job.IngestionTrigger.SCHEDULED,
        skip_post_ingestion_hook: bool = False,
        skip_legacy_extraction_queue: bool = False,
        force_recover_lock: bool = False,
    ) -> IngestionRunSummary:
        self._recover_stale_running_jobs(source_id=source.id)
        self._assert_extraction_contract(source)
        service = self._get_ingestion_service(source)
        lock_token = self._acquire_source_lock(
            source.id,
            force_recover_lock=force_recover_lock,
        )
        lock_heartbeat_task = self._start_source_lock_heartbeat(
            source_id=source.id,
            lock_token=lock_token,
        )

        try:
            job = self._job_repository.save(
                self._create_ingestion_job(source, trigger=trigger),
            )
            running = self._job_repository.save(job.start_execution())
            sync_state_before = self._prepare_sync_state_for_attempt(source)
            run_context = self._build_run_context(
                source=source,
                ingestion_job_id=running.id,
                sync_state=sync_state_before,
            )
            try:
                summary = await asyncio.wait_for(
                    self._invoke_ingestion_service(
                        service=service,
                        source=source,
                        context=run_context,
                    ),
                    timeout=self._ingestion_job_hard_timeout_seconds,
                )
                self._emit_dedup_telemetry(source_id=source.id, summary=summary)
                self._emit_query_generation_telemetry(
                    source_id=source.id,
                    summary=summary,
                )
                if not skip_post_ingestion_hook:
                    await self._run_post_ingestion_hook(
                        source=source,
                        summary=summary,
                    )
                sync_state_after = self._persist_sync_state_on_success(
                    sync_state=sync_state_before,
                    ingestion_job_id=running.id,
                    summary=summary,
                )
                skipped_records = self._int_summary_field(
                    summary,
                    "skipped_records",
                ) + self._int_summary_field(summary, "unchanged_records")
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

                if not skip_legacy_extraction_queue:
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
            except TimeoutError:
                self._mark_running_job_as_timeout_failure(
                    running=running,
                    timeout_seconds=self._ingestion_job_hard_timeout_seconds,
                    timeout_scope="ingestion_job_hard_timeout",
                    timeout_message=(
                        "Ingestion invocation exceeded the hard timeout window"
                    ),
                )
                raise
            except Exception as exc:
                self._handle_ingestion_failure(
                    running=running,
                    source=source,
                    error_message=str(exc),
                )
                raise
            else:
                self._job_repository.save(completed)
                updated_source = (
                    self._source_repository.record_ingestion(source.id) or source
                )
                self._update_schedule_after_run(updated_source)
                return summary
        finally:
            if lock_heartbeat_task is not None:
                lock_heartbeat_task.cancel()
                with suppress(asyncio.CancelledError):
                    await lock_heartbeat_task
            if lock_token is not None:
                self._release_source_lock(source_id=source.id, lock_token=lock_token)

    async def _run_post_ingestion_hook(
        self: IngestionSchedulingService,
        *,
        source: user_data_source.UserDataSource,
        summary: IngestionRunSummary,
    ) -> None:
        hook = self._post_ingestion_hook
        if hook is None:
            return
        try:
            await asyncio.wait_for(
                hook(source, summary),
                timeout=self._post_ingestion_hook_timeout_seconds,
            )
        except TimeoutError as exc:
            logger.exception(
                "Post-ingestion hook timed out",
                extra={
                    "source_id": str(source.id),
                    "timeout_seconds": self._post_ingestion_hook_timeout_seconds,
                },
            )
            msg = (
                "Post-ingestion hook timed out after "
                f"{self._post_ingestion_hook_timeout_seconds}s for source {source.id}"
            )
            raise RuntimeError(msg) from exc
        except Exception as exc:
            logger.exception(
                "Post-ingestion hook failed",
                extra={"source_id": str(source.id)},
            )
            msg = f"Post-ingestion hook failed for source {source.id}: {exc!s}"
            raise RuntimeError(msg) from exc

    def _recover_stale_running_jobs(
        self: IngestionSchedulingService,
        *,
        source_id: UUID | None = None,
        as_of: datetime | None = None,
    ) -> int:
        reference = normalize_datetime(as_of or datetime.now(UTC))
        timeout_seconds = self._scheduler_stale_running_timeout_seconds
        if source_id is None:
            candidates = self._job_repository.find_running_jobs(limit=200)
        else:
            recent_jobs = self._job_repository.find_by_source(source_id, limit=50)
            candidates = [
                job
                for job in recent_jobs
                if job.status == ingestion_job.IngestionStatus.RUNNING
            ]

        stale_jobs = [
            job
            for job in candidates
            if self._is_stale_running_job(job=job, as_of=reference)
        ]
        for stale_job in stale_jobs:
            self._mark_running_job_as_timeout_failure(
                running=stale_job,
                timeout_seconds=timeout_seconds,
                timeout_scope="stale_running_recovery",
                timeout_message=(
                    "Ingestion job remained in RUNNING state beyond stale timeout "
                    "threshold and was recovered automatically"
                ),
                timed_out_at=reference,
            )
        return len(stale_jobs)

    def _is_stale_running_job(
        self: IngestionSchedulingService,
        *,
        job: ingestion_job.IngestionJob,
        as_of: datetime,
    ) -> bool:
        if job.status != ingestion_job.IngestionStatus.RUNNING:
            return False
        started_at = normalize_datetime(job.started_at or job.triggered_at)
        elapsed_seconds = (as_of - started_at).total_seconds()
        return elapsed_seconds >= self._scheduler_stale_running_timeout_seconds

    def _mark_running_job_as_timeout_failure(
        self: IngestionSchedulingService,
        *,
        running: ingestion_job.IngestionJob,
        timeout_seconds: int,
        timeout_scope: str,
        timeout_message: str,
        timed_out_at: datetime | None = None,
    ) -> None:
        failure_time = normalize_datetime(timed_out_at or datetime.now(UTC))
        failure_payload: JSONObject = {
            "error_type": "timeout",
            "timeout_seconds": timeout_seconds,
            "timeout_scope": timeout_scope,
            "timed_out_at": failure_time.isoformat(timespec="seconds"),
        }
        error = ingestion_job.IngestionError(
            error_type="timeout",
            error_message=(
                f"{timeout_message} (timeout_seconds={timeout_seconds}, "
                f"scope={timeout_scope})"
            ),
            error_details=failure_payload,
            record_id=None,
        )
        failed = running.model_copy(
            update={
                "metadata": with_failure_metadata(
                    running.metadata,
                    failure_payload=failure_payload,
                ),
            },
        ).fail(error)
        self._job_repository.save(failed)
        logger.warning(
            "Ingestion job marked as failed due to timeout",
            extra={
                "job_id": str(running.id),
                "source_id": str(running.source_id),
                "timeout_scope": timeout_scope,
                "timeout_seconds": timeout_seconds,
            },
        )

    def _handle_ingestion_failure(
        self: IngestionSchedulingService,
        *,
        running: ingestion_job.IngestionJob,
        source: user_data_source.UserDataSource,
        error_message: str,
    ) -> None:
        error = ingestion_job.IngestionError(
            error_type="scheduler_failure",
            error_message=error_message,
            record_id=None,
        )
        self._rollback_job_repository_session()
        failed = running.fail(error)
        try:
            self._job_repository.save(failed)
        except Exception:  # noqa: BLE001
            logger.exception(
                "Failed to persist ingestion failure state after rollback",
                extra={
                    "job_id": str(running.id),
                    "source_id": str(source.id),
                },
            )

    def _rollback_job_repository_session(self: IngestionSchedulingService) -> None:
        repository_session = getattr(self._job_repository, "session", None)
        if repository_session is None:
            return
        rollback = getattr(repository_session, "rollback", None)
        if callable(rollback):
            rollback()

    def _acquire_source_lock(
        self: IngestionSchedulingService,
        source_id: UUID,
        *,
        force_recover_lock: bool = False,
    ) -> str | None:
        repository = self._source_lock_repository
        if repository is None:
            self._ensure_source_not_running(source_id)
            return None

        now = datetime.now(UTC)
        lock_token = uuid4().hex
        lease_expires_at = now + timedelta(seconds=self._source_lock_lease_ttl_seconds)
        lock = repository.try_acquire(
            source_id=source_id,
            lock_token=lock_token,
            lease_expires_at=lease_expires_at,
            heartbeat_at=now,
            acquired_by=self._source_lock_owner,
        )
        if (
            lock is None
            and force_recover_lock
            and not self._source_has_running_job(source_id)
        ):
            stale_lock = repository.get_by_source(source_id)
            if (
                stale_lock is not None
                and stale_lock.lease_expires_at.astimezone(UTC) <= now
                and repository.delete_by_source(source_id)
            ):
                logger.warning(
                    "Force-recovered source ingestion lock before retry",
                    extra={
                        "source_id": str(source_id),
                        "stale_lock_expires_at": stale_lock.lease_expires_at.isoformat(
                            timespec="seconds",
                        ),
                        "stale_lock_heartbeat_at": stale_lock.last_heartbeat_at.isoformat(
                            timespec="seconds",
                        ),
                    },
                )
                lock = repository.try_acquire(
                    source_id=source_id,
                    lock_token=lock_token,
                    lease_expires_at=lease_expires_at,
                    heartbeat_at=now,
                    acquired_by=self._source_lock_owner,
                )
        if lock is None:
            msg = f"Ingestion already running for source {source_id}"
            raise ValueError(msg)
        return lock_token

    def _start_source_lock_heartbeat(
        self: IngestionSchedulingService,
        *,
        source_id: UUID,
        lock_token: str | None,
    ) -> asyncio.Task[None] | None:
        if lock_token is None or self._source_lock_repository is None:
            return None
        return asyncio.create_task(
            self._run_source_lock_heartbeat(
                source_id=source_id,
                lock_token=lock_token,
            ),
            name=f"ingestion-source-lock-heartbeat-{source_id}",
        )

    async def _run_source_lock_heartbeat(
        self: IngestionSchedulingService,
        *,
        source_id: UUID,
        lock_token: str,
    ) -> None:
        repository = self._source_lock_repository
        if repository is None:
            return
        while True:
            await asyncio.sleep(self._source_lock_heartbeat_seconds)
            heartbeat_at = datetime.now(UTC)
            lease_expires_at = heartbeat_at + timedelta(
                seconds=self._source_lock_lease_ttl_seconds,
            )
            refreshed = repository.refresh_lease(
                source_id=source_id,
                lock_token=lock_token,
                lease_expires_at=lease_expires_at,
                heartbeat_at=heartbeat_at,
            )
            if refreshed is None:
                logger.warning(
                    "Lost source ingestion lock lease before run completed",
                    extra={"source_id": str(source_id)},
                )
                return

    def _release_source_lock(
        self: IngestionSchedulingService,
        *,
        source_id: UUID,
        lock_token: str,
    ) -> None:
        repository = self._source_lock_repository
        if repository is None:
            return
        released = repository.release(
            source_id=source_id,
            lock_token=lock_token,
        )
        if not released:
            logger.warning(
                "Source ingestion lock release skipped because ownership no longer matched",
                extra={"source_id": str(source_id)},
            )

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
