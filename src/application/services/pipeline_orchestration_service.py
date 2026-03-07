"""Unified orchestration service for end-to-end source pipeline execution."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from src.application.services._pipeline_failure_classification import (
    resolve_pipeline_error_category,
)
from src.domain.entities.ingestion_job import (
    IngestionError,
    IngestionJob,
    IngestionJobKind,
    IngestionStatus,
    IngestionTrigger,
)
from src.domain.value_objects.provenance import DataSource, Provenance
from src.type_definitions.json_utils import to_json_value

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from src.type_definitions.common import JSONObject

from src.application.services._pipeline_orchestration_checkpoint_helpers import (
    _PipelineOrchestrationCheckpointHelpers,
)
from src.application.services._pipeline_orchestration_contracts import (
    PipelineRunSummary,
    PipelineStageName,
    PipelineStageStatus,
)
from src.application.services._pipeline_orchestration_execution_helpers import (
    _PipelineOrchestrationExecutionHelpers,
)

if TYPE_CHECKING:
    from src.application.agents.services._content_enrichment_types import (
        ContentEnrichmentRunSummary,
    )
    from src.application.agents.services.content_enrichment_service import (
        ContentEnrichmentService,
    )
    from src.application.agents.services.entity_recognition_service import (
        EntityRecognitionRunSummary,
        EntityRecognitionService,
    )
    from src.application.agents.services.graph_connection_service import (
        GraphConnectionOutcome,
        GraphConnectionService,
    )
    from src.application.agents.services.graph_search_service import (
        GraphSearchService,
    )
    from src.application.services.ingestion_scheduling_service import (
        IngestionSchedulingService,
    )
    from src.domain.repositories.ingestion_job_repository import IngestionJobRepository
    from src.domain.repositories.research_space_repository import (
        ResearchSpaceRepository,
    )

logger = logging.getLogger(__name__)

_ENV_PIPELINE_QUEUE_MAX_SIZE = "MED13_PIPELINE_QUEUE_MAX_SIZE"
_DEFAULT_PIPELINE_QUEUE_MAX_SIZE = 100
_ENV_PIPELINE_QUEUE_RETRY_AFTER_SECONDS = "MED13_PIPELINE_QUEUE_RETRY_AFTER_SECONDS"
_DEFAULT_PIPELINE_QUEUE_RETRY_AFTER_SECONDS = 30
_ENV_PIPELINE_RETRY_MAX_ATTEMPTS = "MED13_PIPELINE_RETRY_MAX_ATTEMPTS"
_DEFAULT_PIPELINE_RETRY_MAX_ATTEMPTS = 5
_ENV_PIPELINE_RETRY_BASE_DELAY_SECONDS = "MED13_PIPELINE_RETRY_BASE_DELAY_SECONDS"
_DEFAULT_PIPELINE_RETRY_BASE_DELAY_SECONDS = 30


def _read_positive_int_env(env_name: str, *, default_value: int) -> int:
    raw_value = os.getenv(env_name)
    if raw_value is None or not raw_value.strip():
        return default_value
    try:
        parsed = int(raw_value.strip())
    except ValueError:
        logger.warning(
            "Invalid integer override in %s=%r; using default %d",
            env_name,
            raw_value,
            default_value,
        )
        return default_value
    if parsed <= 0:
        logger.warning(
            "Non-positive integer override in %s=%r; using default %d",
            env_name,
            raw_value,
            default_value,
        )
        return default_value
    return parsed


class ActivePipelineRunExistsError(RuntimeError):
    """Raised when a source already has queued or running pipeline work."""

    def __init__(self, *, run_id: str) -> None:
        self.run_id = run_id
        super().__init__(
            "An active pipeline run already exists for this source "
            f"(run_id={run_id})",
        )


class PipelineQueueFullError(RuntimeError):
    """Raised when the durable pipeline queue is at capacity."""

    def __init__(self, *, retry_after_seconds: int) -> None:
        self.retry_after_seconds = retry_after_seconds
        super().__init__("Pipeline queue is full")


@dataclass(frozen=True)
class QueuedPipelineRunRequest:
    """Resolved pipeline arguments stored in durable queue metadata."""

    run_id: str
    research_space_id: UUID
    resume_from_stage: PipelineStageName | None
    enrichment_limit: int
    extraction_limit: int
    source_type: str | None
    model_id: str | None
    shadow_mode: bool | None
    force_recover_lock: bool
    graph_seed_entity_ids: list[str] | None
    graph_max_depth: int
    graph_relation_types: list[str] | None


@dataclass(frozen=True)
class PipelineRunEnqueueResult:
    """Accepted durable queue response for async pipeline runs."""

    run_id: str
    source_id: UUID
    research_space_id: UUID
    status: str
    accepted_at: datetime


@dataclass(frozen=True)
class PipelineOrchestrationDependencies:
    """Dependencies required for end-to-end pipeline orchestration."""

    ingestion_scheduling_service: IngestionSchedulingService
    content_enrichment_service: ContentEnrichmentService
    entity_recognition_service: EntityRecognitionService
    content_enrichment_stage_runner: (
        Callable[..., Awaitable[ContentEnrichmentRunSummary]] | None
    ) = None
    entity_recognition_stage_runner: (
        Callable[..., Awaitable[EntityRecognitionRunSummary]] | None
    ) = None
    graph_connection_service: GraphConnectionService | None = None
    graph_connection_seed_runner: (
        Callable[..., Awaitable[GraphConnectionOutcome]] | None
    ) = None
    graph_search_service: GraphSearchService | None = None
    research_space_repository: ResearchSpaceRepository | None = None
    pipeline_run_repository: IngestionJobRepository | None = None


class PipelineOrchestrationService(
    _PipelineOrchestrationExecutionHelpers,
    _PipelineOrchestrationCheckpointHelpers,
):
    """Run ingestion -> enrichment -> extraction -> graph stages with one run id."""

    def __init__(self, dependencies: PipelineOrchestrationDependencies) -> None:
        self._ingestion = dependencies.ingestion_scheduling_service
        self._enrichment = dependencies.content_enrichment_service
        self._extraction = dependencies.entity_recognition_service
        self._enrichment_stage_runner = dependencies.content_enrichment_stage_runner
        self._extraction_stage_runner = dependencies.entity_recognition_stage_runner
        self._graph = dependencies.graph_connection_service
        self._graph_seed_runner = dependencies.graph_connection_seed_runner
        self._graph_search = dependencies.graph_search_service
        self._research_spaces = dependencies.research_space_repository
        self._pipeline_runs = dependencies.pipeline_run_repository

    def enqueue_run(  # noqa: PLR0913
        self,
        *,
        source_id: UUID,
        research_space_id: UUID,
        run_id: str | None = None,
        resume_from_stage: PipelineStageName | None = None,
        enrichment_limit: int = 25,
        extraction_limit: int = 25,
        source_type: str | None = None,
        model_id: str | None = None,
        shadow_mode: bool | None = None,
        force_recover_lock: bool = False,
        graph_seed_entity_ids: list[str] | None = None,
        graph_max_depth: int = 2,
        graph_relation_types: list[str] | None = None,
    ) -> PipelineRunEnqueueResult:
        repository = self._require_pipeline_repository()
        normalized_run_id = self._resolve_run_id(run_id)
        active_job = repository.find_active_pipeline_job_for_source(
            source_id=source_id,
        )
        if active_job is not None:
            active_run_id = self._resolve_pipeline_run_id_from_job(active_job)
            raise ActivePipelineRunExistsError(run_id=active_run_id)

        queue_max_size = _read_positive_int_env(
            _ENV_PIPELINE_QUEUE_MAX_SIZE,
            default_value=_DEFAULT_PIPELINE_QUEUE_MAX_SIZE,
        )
        if repository.count_active_pipeline_queue_jobs() >= queue_max_size:
            raise PipelineQueueFullError(
                retry_after_seconds=_read_positive_int_env(
                    _ENV_PIPELINE_QUEUE_RETRY_AFTER_SECONDS,
                    default_value=_DEFAULT_PIPELINE_QUEUE_RETRY_AFTER_SECONDS,
                ),
            )

        normalized_resume_stage = self._resolve_resume_stage(resume_from_stage)
        accepted_at = datetime.now(UTC)
        requested_args = self._build_requested_args_payload(
            resume_from_stage=normalized_resume_stage,
            enrichment_limit=enrichment_limit,
            extraction_limit=extraction_limit,
            source_type=source_type,
            model_id=model_id,
            shadow_mode=shadow_mode,
            force_recover_lock=force_recover_lock,
            graph_seed_entity_ids=graph_seed_entity_ids,
            graph_max_depth=graph_max_depth,
            graph_relation_types=graph_relation_types,
        )
        metadata = self._build_pipeline_metadata(
            existing_metadata={},
            run_id=normalized_run_id,
            research_space_id=research_space_id,
            resume_from_stage=normalized_resume_stage,
            overall_status="queued",
            stage_updates={},
        )
        metadata = self._update_pipeline_metadata_fields(
            existing_metadata=metadata,
            requested_args=requested_args,
            accepted_at=accepted_at.isoformat(timespec="seconds"),
            attempt_count=0,
            next_attempt_at=None,
            worker_id=None,
            last_error=None,
            error_category=None,
        )
        job = IngestionJob(
            id=uuid4(),
            source_id=source_id,
            job_kind=IngestionJobKind.PIPELINE_ORCHESTRATION,
            trigger=IngestionTrigger.API,
            triggered_by=None,
            triggered_at=accepted_at,
            status=IngestionStatus.PENDING,
            started_at=None,
            completed_at=None,
            provenance=Provenance(
                source=DataSource.COMPUTED,
                source_version=None,
                source_url=None,
                acquired_by="pipeline_orchestration_service",
                processing_steps=("pipeline_orchestration", "queued_execution"),
                quality_score=None,
                metadata={"run_id": normalized_run_id},
            ),
            metadata=metadata,
            source_config_snapshot={},
        )
        saved_job = repository.save(job)
        return PipelineRunEnqueueResult(
            run_id=normalized_run_id,
            source_id=saved_job.source_id,
            research_space_id=research_space_id,
            status="queued",
            accepted_at=accepted_at,
        )

    def claim_next_queued_run(
        self,
        *,
        worker_id: str,
        as_of: datetime | None = None,
    ) -> IngestionJob | None:
        repository = self._require_pipeline_repository()
        return repository.claim_next_pipeline_job(
            worker_id=worker_id,
            as_of=as_of or datetime.now(UTC),
        )

    def heartbeat_claimed_run(
        self,
        *,
        job_id: UUID,
        worker_id: str,
        heartbeat_at: datetime | None = None,
    ) -> IngestionJob | None:
        repository = self._require_pipeline_repository()
        return repository.heartbeat_pipeline_job(
            job_id=job_id,
            worker_id=worker_id,
            heartbeat_at=heartbeat_at or datetime.now(UTC),
        )

    async def run_next_queued_job(
        self,
        *,
        worker_id: str,
    ) -> bool:
        repository = self._require_pipeline_repository()
        claimed_job = repository.claim_next_pipeline_job(
            worker_id=worker_id,
            as_of=datetime.now(UTC),
        )
        if claimed_job is None:
            return False
        await self.execute_claimed_run(claimed_job=claimed_job, worker_id=worker_id)
        return True

    async def execute_claimed_run(
        self,
        *,
        claimed_job: IngestionJob,
        worker_id: str,
    ) -> None:
        repository = self._require_pipeline_repository()

        queued_request = self._resolve_queued_request(claimed_job)
        try:
            summary = await self.run_for_source(
                source_id=claimed_job.source_id,
                research_space_id=queued_request.research_space_id,
                run_id=queued_request.run_id,
                resume_from_stage=queued_request.resume_from_stage,
                enrichment_limit=queued_request.enrichment_limit,
                extraction_limit=queued_request.extraction_limit,
                source_type=queued_request.source_type,
                model_id=queued_request.model_id,
                shadow_mode=queued_request.shadow_mode,
                force_recover_lock=queued_request.force_recover_lock,
                graph_seed_entity_ids=queued_request.graph_seed_entity_ids,
                graph_max_depth=queued_request.graph_max_depth,
                graph_relation_types=queued_request.graph_relation_types,
            )
        except Exception as exc:  # noqa: BLE001 - worker must settle queue state
            error_message = str(exc).strip() or exc.__class__.__name__
            error_category = resolve_pipeline_error_category((error_message,))
            if error_category == "capacity" and self._should_retry_job(claimed_job):
                self._mark_job_retryable(
                    job_id=claimed_job.id,
                    worker_id=worker_id,
                    attempt_count=self._resolve_pipeline_attempt_count(claimed_job),
                    last_error=error_message,
                    error_category=error_category,
                )
            else:
                self._mark_claimed_job_failed(
                    claimed_job=claimed_job,
                    worker_id=worker_id,
                    error_message=error_message,
                    error_category=error_category,
                )
            return

        error_category = resolve_pipeline_error_category(summary.errors)
        if summary.status == "failed" and error_category == "capacity":
            current_job = repository.find_by_id(claimed_job.id) or claimed_job
            if self._should_retry_job(current_job):
                self._mark_job_retryable(
                    job_id=claimed_job.id,
                    worker_id=worker_id,
                    attempt_count=self._resolve_pipeline_attempt_count(current_job),
                    last_error=summary.errors[-1] if summary.errors else "capacity",
                    error_category=error_category,
                )
        return

    def cancel_run(
        self,
        *,
        source_id: UUID,
        run_id: str,
    ) -> IngestionJob | None:
        normalized_run_id = run_id.strip()
        if not normalized_run_id:
            return None
        return self._cancel_pipeline_run(
            source_id=source_id,
            run_id=normalized_run_id,
        )

    def _require_pipeline_repository(self) -> IngestionJobRepository:
        if self._pipeline_runs is None:
            msg = "Pipeline run repository is not configured"
            raise RuntimeError(msg)
        return self._pipeline_runs

    def _mark_job_retryable(
        self,
        *,
        job_id: UUID,
        worker_id: str,
        attempt_count: int,
        last_error: str,
        error_category: str | None,
    ) -> IngestionJob | None:
        retry_delay_seconds = _read_positive_int_env(
            _ENV_PIPELINE_RETRY_BASE_DELAY_SECONDS,
            default_value=_DEFAULT_PIPELINE_RETRY_BASE_DELAY_SECONDS,
        ) * (2 ** max(attempt_count, 0))
        return self._require_pipeline_repository().mark_pipeline_job_retryable(
            job_id=job_id,
            worker_id=worker_id,
            next_attempt_at=datetime.now(UTC) + timedelta(seconds=retry_delay_seconds),
            last_error=last_error,
            error_category=error_category,
        )

    def _mark_claimed_job_failed(
        self,
        *,
        claimed_job: IngestionJob,
        worker_id: str,
        error_message: str,
        error_category: str | None,
    ) -> IngestionJob:
        repository = self._require_pipeline_repository()
        current_job = repository.find_by_id(claimed_job.id) or claimed_job
        failed_job = current_job.fail(
            IngestionError(
                error_type="pipeline_worker_failed",
                error_message=error_message,
                error_details={
                    "worker_id": worker_id,
                    "error_category": error_category,
                },
                record_id=None,
            ),
        )
        updated_metadata = self._update_pipeline_metadata_fields(
            existing_metadata=failed_job.metadata,
            status="failed",
            queue_status="failed",
            worker_id=worker_id,
            last_error=error_message,
            error_category=error_category,
            completed_at=datetime.now(UTC).isoformat(timespec="seconds"),
        )
        return repository.save(
            failed_job.model_copy(update={"metadata": updated_metadata}),
        )

    def _should_retry_job(self, job: IngestionJob) -> bool:
        max_attempts = _read_positive_int_env(
            _ENV_PIPELINE_RETRY_MAX_ATTEMPTS,
            default_value=_DEFAULT_PIPELINE_RETRY_MAX_ATTEMPTS,
        )
        return self._resolve_pipeline_attempt_count(job) < max_attempts

    def _resolve_pipeline_run_id_from_job(self, job: IngestionJob) -> str:
        pipeline_payload = self._pipeline_payload(job.metadata)
        raw_run_id = pipeline_payload.get("run_id")
        if isinstance(raw_run_id, str) and raw_run_id.strip():
            return raw_run_id.strip()
        return str(job.id)

    def _resolve_pipeline_attempt_count(self, job: IngestionJob) -> int:
        pipeline_payload = self._pipeline_payload(job.metadata)
        raw_attempt_count = pipeline_payload.get("attempt_count")
        if isinstance(raw_attempt_count, int):
            return max(raw_attempt_count, 0)
        if isinstance(raw_attempt_count, float):
            return max(int(raw_attempt_count), 0)
        if isinstance(raw_attempt_count, str):
            try:
                return max(int(raw_attempt_count.strip()), 0)
            except ValueError:
                return 0
        return 0

    def _resolve_queued_request(self, job: IngestionJob) -> QueuedPipelineRunRequest:
        pipeline_payload = self._pipeline_payload(job.metadata)
        research_space_id_raw = pipeline_payload.get("research_space_id")
        if (
            not isinstance(research_space_id_raw, str)
            or not research_space_id_raw.strip()
        ):
            msg = f"Queued pipeline job {job.id} is missing research_space_id"
            raise RuntimeError(msg)
        try:
            research_space_id = UUID(research_space_id_raw.strip())
        except ValueError as exc:
            msg = f"Queued pipeline job {job.id} has invalid research_space_id"
            raise RuntimeError(msg) from exc

        requested_args = self._coerce_json_object(
            pipeline_payload.get("requested_args"),
        )
        raw_shadow_mode = requested_args.get("shadow_mode")
        return QueuedPipelineRunRequest(
            run_id=self._resolve_pipeline_run_id_from_job(job),
            research_space_id=research_space_id,
            resume_from_stage=self._resolve_resume_stage(
                self._normalize_optional_stage(requested_args.get("resume_from_stage")),
            ),
            enrichment_limit=self._coerce_positive_int(
                requested_args.get("enrichment_limit"),
                default_value=25,
            ),
            extraction_limit=self._coerce_positive_int(
                requested_args.get("extraction_limit"),
                default_value=25,
            ),
            source_type=self._normalize_optional_string(
                requested_args.get("source_type"),
            ),
            model_id=self._normalize_optional_string(requested_args.get("model_id")),
            shadow_mode=raw_shadow_mode if isinstance(raw_shadow_mode, bool) else None,
            force_recover_lock=requested_args.get("force_recover_lock") is True,
            graph_seed_entity_ids=self._coerce_string_list(
                requested_args.get("graph_seed_entity_ids"),
            ),
            graph_max_depth=self._coerce_positive_int(
                requested_args.get("graph_max_depth"),
                default_value=2,
            ),
            graph_relation_types=self._coerce_string_list(
                requested_args.get("graph_relation_types"),
            ),
        )

    @staticmethod
    def _build_requested_args_payload(  # noqa: PLR0913
        *,
        resume_from_stage: PipelineStageName | None,
        enrichment_limit: int,
        extraction_limit: int,
        source_type: str | None,
        model_id: str | None,
        shadow_mode: bool | None,
        force_recover_lock: bool,
        graph_seed_entity_ids: list[str] | None,
        graph_max_depth: int,
        graph_relation_types: list[str] | None,
    ) -> JSONObject:
        payload: JSONObject = {
            "resume_from_stage": to_json_value(resume_from_stage),
            "enrichment_limit": max(enrichment_limit, 1),
            "extraction_limit": max(extraction_limit, 1),
            "source_type": to_json_value(source_type),
            "model_id": to_json_value(model_id),
            "shadow_mode": to_json_value(shadow_mode),
            "force_recover_lock": force_recover_lock,
            "graph_seed_entity_ids": (
                [to_json_value(item) for item in graph_seed_entity_ids]
                if graph_seed_entity_ids is not None
                else None
            ),
            "graph_max_depth": max(graph_max_depth, 1),
            "graph_relation_types": (
                [to_json_value(item) for item in graph_relation_types]
                if graph_relation_types is not None
                else None
            ),
        }
        return payload

    def _update_pipeline_metadata_fields(
        self,
        *,
        existing_metadata: object,
        **fields: object,
    ) -> JSONObject:
        metadata = self._coerce_json_object(existing_metadata)
        pipeline_payload = self._pipeline_payload(existing_metadata)
        for key, value in fields.items():
            pipeline_payload[str(key)] = to_json_value(value)
        metadata["pipeline_run"] = pipeline_payload
        return metadata

    def _pipeline_payload(self, metadata: object) -> JSONObject:
        raw_metadata = self._coerce_json_object(metadata)
        raw_pipeline = raw_metadata.get("pipeline_run")
        return self._coerce_json_object(raw_pipeline)

    @staticmethod
    def _coerce_string_list(raw_value: object) -> list[str] | None:
        if raw_value is None:
            return None
        if not isinstance(raw_value, list):
            return None
        normalized_values: list[str] = []
        for item in raw_value:
            if not isinstance(item, str):
                continue
            normalized = item.strip()
            if not normalized or normalized in normalized_values:
                continue
            normalized_values.append(normalized)
        return normalized_values or None

    @staticmethod
    def _normalize_optional_string(raw_value: object) -> str | None:
        if not isinstance(raw_value, str):
            return None
        normalized = raw_value.strip()
        return normalized or None

    @staticmethod
    def _normalize_optional_stage(raw_value: object) -> PipelineStageName | None:
        if not isinstance(raw_value, str):
            return None
        normalized = raw_value.strip()
        if normalized == "ingestion":
            return "ingestion"
        if normalized == "enrichment":
            return "enrichment"
        if normalized == "extraction":
            return "extraction"
        if normalized == "graph":
            return "graph"
        return None

    @staticmethod
    def _coerce_positive_int(raw_value: object, *, default_value: int) -> int:
        if isinstance(raw_value, int) and raw_value > 0:
            return raw_value
        if isinstance(raw_value, float) and raw_value > 0:
            return int(raw_value)
        if isinstance(raw_value, str):
            try:
                parsed = int(raw_value.strip())
            except ValueError:
                return default_value
            if parsed > 0:
                return parsed
        return default_value


__all__ = [
    "ActivePipelineRunExistsError",
    "PipelineOrchestrationDependencies",
    "PipelineQueueFullError",
    "PipelineRunEnqueueResult",
    "PipelineOrchestrationService",
    "PipelineRunSummary",
    "PipelineStageName",
    "PipelineStageStatus",
]
