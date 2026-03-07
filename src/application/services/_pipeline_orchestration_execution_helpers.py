"""Execution helpers for unified pipeline orchestration."""

# mypy: disable-error-code="misc"

from __future__ import annotations

import asyncio
import logging
import os
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Literal

from src.application.services._pipeline_failure_classification import (
    resolve_pipeline_error_category,
)
from src.application.services._pipeline_orchestration_contracts import (
    PipelineRunSummary,
    PipelineStageName,
    PipelineStageStatus,
)
from src.application.services._pipeline_orchestration_graph_fallback_helpers import (
    extract_graph_fallback_relations_from_extraction_summary,
    resolve_latest_ingestion_job_id,
)
from src.application.services._pipeline_orchestration_graph_stage_helpers import (
    _GraphStageInput,
    _PipelineOrchestrationGraphStageHelpers,
)
from src.application.services._pipeline_orchestration_seed_helpers import (
    _PipelineOrchestrationContextSeedHelpers,
)

if TYPE_CHECKING:
    from uuid import UUID

    from src.application.agents.services._content_enrichment_types import (
        ContentEnrichmentRunSummary,
    )
    from src.application.agents.services.entity_recognition_service import (
        EntityRecognitionRunSummary,
    )
    from src.application.services._pipeline_orchestration_execution_protocols import (
        _PipelineExecutionSelf,
    )
    from src.domain.agents.contracts.graph_connection import ProposedRelation

logger = logging.getLogger(__name__)

_ENV_EXTRACTION_STAGE_WATCHDOG_TIMEOUT_SECONDS = (
    "MED13_PIPELINE_EXTRACTION_STAGE_TIMEOUT_SECONDS"
)
_DEFAULT_EXTRACTION_STAGE_WATCHDOG_TIMEOUT_SECONDS = 900.0
_ENV_ENTITY_RECOGNITION_AGENT_TIMEOUT_SECONDS = (
    "MED13_ENTITY_RECOGNITION_AGENT_TIMEOUT_SECONDS"
)
_DEFAULT_ENTITY_RECOGNITION_AGENT_TIMEOUT_SECONDS = 180.0
_ENV_ENTITY_RECOGNITION_EXTRACTION_STAGE_TIMEOUT_SECONDS = (
    "MED13_ENTITY_RECOGNITION_EXTRACTION_STAGE_TIMEOUT_SECONDS"
)
_DEFAULT_ENTITY_RECOGNITION_EXTRACTION_STAGE_TIMEOUT_SECONDS = 300.0
_ENV_ENTITY_RECOGNITION_BATCH_MAX_CONCURRENCY = (
    "MED13_ENTITY_RECOGNITION_BATCH_MAX_CONCURRENCY"
)
_DEFAULT_ENTITY_RECOGNITION_BATCH_MAX_CONCURRENCY = 2
_EXTRACTION_STAGE_TIMEOUT_OVERHEAD_SECONDS = 15.0
_ENV_GRAPH_SEED_INFERENCE_TIMEOUT_SECONDS = (
    "MED13_PIPELINE_GRAPH_SEED_INFERENCE_TIMEOUT_SECONDS"
)
_DEFAULT_GRAPH_SEED_INFERENCE_TIMEOUT_SECONDS = 120.0
_ENV_EXTRACTION_FAILURE_RATIO_THRESHOLD = (
    "MED13_PIPELINE_EXTRACTION_FAILURE_RATIO_THRESHOLD"
)
_DEFAULT_EXTRACTION_FAILURE_RATIO_THRESHOLD = 1.0
_ENV_EXTRACTION_FAILURE_RATIO_THRESHOLD_PUBMED = (
    "MED13_PIPELINE_EXTRACTION_FAILURE_RATIO_THRESHOLD_PUBMED"
)
_DEFAULT_EXTRACTION_FAILURE_RATIO_THRESHOLD_PUBMED = 0.0


def _read_positive_timeout_seconds(
    env_name: str,
    *,
    default_seconds: float,
) -> float:
    raw_value = os.getenv(env_name)
    if raw_value is None:
        return default_seconds
    try:
        parsed = float(raw_value)
    except ValueError:
        logger.warning(
            "Invalid timeout override in %s=%r; using default %.1fs",
            env_name,
            raw_value,
            default_seconds,
        )
        return default_seconds
    if parsed <= 0:
        logger.warning(
            "Non-positive timeout override in %s=%r; using default %.1fs",
            env_name,
            raw_value,
            default_seconds,
        )
        return default_seconds
    return parsed


def _read_positive_int(
    env_name: str,
    *,
    default_value: int,
) -> int:
    raw_value = os.getenv(env_name)
    if raw_value is None:
        return default_value
    try:
        parsed = int(raw_value)
    except ValueError:
        logger.warning(
            "Invalid integer override in %s=%r; using default %s",
            env_name,
            raw_value,
            default_value,
        )
        return default_value
    if parsed <= 0:
        logger.warning(
            "Non-positive integer override in %s=%r; using default %s",
            env_name,
            raw_value,
            default_value,
        )
        return default_value
    return parsed


def _read_failure_ratio_threshold(
    env_name: str,
    *,
    default_value: float,
) -> float:
    raw_value = os.getenv(env_name)
    if raw_value is None:
        return default_value
    try:
        parsed = float(raw_value)
    except ValueError:
        logger.warning(
            "Invalid ratio override in %s=%r; using default %.3f",
            env_name,
            raw_value,
            default_value,
        )
        return default_value
    if parsed < 0:
        logger.warning(
            "Negative ratio override in %s=%r; clamping to 0.0",
            env_name,
            raw_value,
        )
        return 0.0
    if parsed > 1:
        logger.warning(
            "Ratio override above 1.0 in %s=%r; clamping to 1.0",
            env_name,
            raw_value,
        )
        return 1.0
    return parsed


def _resolve_extraction_failure_ratio_threshold(source_type: str | None) -> float:
    normalized_source_type = source_type.strip().lower() if source_type else None
    if normalized_source_type == "pubmed":
        return _read_failure_ratio_threshold(
            _ENV_EXTRACTION_FAILURE_RATIO_THRESHOLD_PUBMED,
            default_value=_DEFAULT_EXTRACTION_FAILURE_RATIO_THRESHOLD_PUBMED,
        )
    return _read_failure_ratio_threshold(
        _ENV_EXTRACTION_FAILURE_RATIO_THRESHOLD,
        default_value=_DEFAULT_EXTRACTION_FAILURE_RATIO_THRESHOLD,
    )


def _coerce_optional_uuid(raw_value: object) -> UUID | None:
    if raw_value is None:
        return None
    import uuid

    if isinstance(raw_value, uuid.UUID):
        return raw_value
    if isinstance(raw_value, str):
        normalized = raw_value.strip()
        if not normalized:
            return None
        try:
            return uuid.UUID(normalized)
        except ValueError:
            return None
    return None


def _first_matching_error(
    messages: tuple[str, ...] | list[str],
    *,
    category: str | None,
) -> str | None:
    if category is None:
        return None
    for message in messages:
        if resolve_pipeline_error_category((message,)) == category:
            return message
    return None


class _PipelineOrchestrationExecutionHelpers(
    _PipelineOrchestrationContextSeedHelpers,
    _PipelineOrchestrationGraphStageHelpers,
):
    """Execution-stage helpers for unified pipeline runs."""

    async def run_for_source(  # noqa: C901, PLR0912, PLR0913, PLR0915
        self: _PipelineExecutionSelf,
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
    ) -> PipelineRunSummary:
        started_at = datetime.now(UTC)
        normalized_run_id = self._resolve_run_id(run_id)
        normalized_resume_stage = self._resolve_resume_stage(resume_from_stage)
        errors: list[str] = []
        pipeline_error_category: str | None = None
        logger.info(
            "Pipeline run started",
            extra={
                "run_id": normalized_run_id,
                "source_id": str(source_id),
                "research_space_id": str(research_space_id),
                "resume_from_stage": normalized_resume_stage,
                "source_type": source_type,
                "enrichment_limit": enrichment_limit,
                "extraction_limit": extraction_limit,
                "graph_max_depth": graph_max_depth,
                "graph_relation_types": graph_relation_types,
                "graph_seed_entity_ids_count": (
                    len(graph_seed_entity_ids) if graph_seed_entity_ids else 0
                ),
            },
        )

        ingestion_status: PipelineStageStatus = "skipped"
        enrichment_status: PipelineStageStatus = "skipped"
        extraction_status: PipelineStageStatus = "skipped"
        graph_status: PipelineStageStatus = "skipped"

        fetched_records = 0
        parsed_publications = 0
        created_publications = 0
        updated_publications = 0
        executed_query: str | None = None
        query_generation_execution_mode: str | None = None
        query_generation_fallback_reason: str | None = None

        enrichment_processed = 0
        enrichment_enriched = 0
        enrichment_failed = 0
        enrichment_ai_runs = 0
        enrichment_deterministic_runs = 0

        extraction_processed = 0
        extraction_extracted = 0
        extraction_failed = 0
        extraction_persisted_relations = 0
        extraction_concept_members_created = 0
        extraction_concept_aliases_created = 0
        extraction_concept_decisions_proposed = 0
        extraction_failure_ratio = 0.0
        extraction_failure_ratio_threshold: float | None = None
        extraction_quality_gate_failed = False

        explicit_graph_seed_entity_ids = self._normalize_graph_seed_entity_ids(
            graph_seed_entity_ids,
        )
        derived_graph_seed_entity_ids: list[str] = []
        extraction_graph_fallback_relations: dict[
            str,
            tuple[ProposedRelation, ...],
        ] = {}
        inferred_graph_seed_entity_ids: list[str] = []
        active_graph_seed_entity_ids = list(explicit_graph_seed_entity_ids)
        graph_seed_mode = "explicit" if explicit_graph_seed_entity_ids else "none"
        graph_requested = len(active_graph_seed_entity_ids)
        graph_processed = 0
        graph_stage_persisted_relations = 0
        total_persisted_relations = 0
        run_cancelled = False
        active_ingestion_job_id: UUID | None = None
        pipeline_run_job = self._start_or_resume_pipeline_run(
            source_id=source_id,
            research_space_id=research_space_id,
            run_id=normalized_run_id,
            resume_from_stage=normalized_resume_stage,
        )
        run_cancelled = self._is_pipeline_run_cancelled(
            source_id=source_id,
            run_id=normalized_run_id,
        )

        should_run_ingestion = self._should_run_stage(
            stage="ingestion",
            resume_from_stage=normalized_resume_stage,
        )
        should_run_enrichment = self._should_run_stage(
            stage="enrichment",
            resume_from_stage=normalized_resume_stage,
        )
        should_run_extraction = self._should_run_stage(
            stage="extraction",
            resume_from_stage=normalized_resume_stage,
        )
        should_run_graph = self._should_run_stage(
            stage="graph",
            resume_from_stage=normalized_resume_stage,
        )

        if should_run_ingestion and not run_cancelled:
            ingestion_started_at = datetime.now(UTC)
            logger.info(
                "Pipeline stage started",
                extra={
                    "run_id": normalized_run_id,
                    "source_id": str(source_id),
                    "stage": "ingestion",
                },
            )
            try:
                try:
                    ingestion_summary = await self._ingestion.trigger_ingestion(
                        source_id,
                        skip_post_ingestion_hook=True,
                        skip_legacy_extraction_queue=True,
                        force_recover_lock=force_recover_lock,
                    )
                except TypeError as exc:
                    if (
                        "skip_post_ingestion_hook"
                        not in str(
                            exc,
                        )
                        and "force_recover_lock"
                        not in str(
                            exc,
                        )
                        and "skip_legacy_extraction_queue" not in str(exc)
                    ):
                        raise
                    ingestion_summary = await self._ingestion.trigger_ingestion(
                        source_id,
                    )
                ingestion_status = "completed"
                fetched_records = ingestion_summary.fetched_records
                parsed_publications = ingestion_summary.parsed_publications
                created_publications = ingestion_summary.created_publications
                updated_publications = ingestion_summary.updated_publications
                executed_query = ingestion_summary.executed_query
                execution_mode = getattr(
                    ingestion_summary,
                    "query_generation_execution_mode",
                    None,
                )
                query_generation_execution_mode = (
                    execution_mode.strip()
                    if isinstance(execution_mode, str) and execution_mode.strip()
                    else None
                )
                fallback_reason = getattr(
                    ingestion_summary,
                    "query_generation_fallback_reason",
                    None,
                )
                query_generation_fallback_reason = (
                    fallback_reason.strip()
                    if isinstance(fallback_reason, str) and fallback_reason.strip()
                    else None
                )
                active_ingestion_job_id = _coerce_optional_uuid(
                    getattr(ingestion_summary, "ingestion_job_id", None),
                )
                if active_ingestion_job_id is None:
                    active_ingestion_job_id = resolve_latest_ingestion_job_id(
                        ingestion_service=self._ingestion,
                        source_id=source_id,
                    )
                if active_ingestion_job_id is None:
                    logger.warning(
                        "Pipeline ingestion completed but no ingestion job id was resolved",
                        extra={
                            "run_id": normalized_run_id,
                            "source_id": str(source_id),
                        },
                    )
                else:
                    pipeline_run_job = self._persist_pipeline_run_progress(
                        run_job=pipeline_run_job,
                        source_id=source_id,
                        research_space_id=research_space_id,
                        run_id=normalized_run_id,
                        resume_from_stage=normalized_resume_stage,
                        progress_key="run_scope",
                        progress_payload={
                            "ingestion_job_id": str(active_ingestion_job_id),
                        },
                        overall_status="running",
                    )
            except Exception as exc:  # noqa: BLE001 - surfaced in run summary
                ingestion_status = "failed"
                error_message = str(exc).strip() or exc.__class__.__name__
                errors.append(f"ingestion:{error_message}")
                pipeline_error_category = resolve_pipeline_error_category(errors)
            ingestion_duration_ms = int(
                (datetime.now(UTC) - ingestion_started_at).total_seconds() * 1000,
            )
            logger.info(
                "Pipeline stage finished",
                extra={
                    "run_id": normalized_run_id,
                    "source_id": str(source_id),
                    "stage": "ingestion",
                    "stage_status": ingestion_status,
                    "duration_ms": ingestion_duration_ms,
                    "fetched_records": fetched_records,
                    "parsed_publications": parsed_publications,
                    "created_publications": created_publications,
                    "updated_publications": updated_publications,
                    "ingestion_job_id": (
                        str(active_ingestion_job_id)
                        if active_ingestion_job_id is not None
                        else None
                    ),
                },
            )
            pipeline_run_job = self._persist_pipeline_stage_checkpoint(
                run_job=pipeline_run_job,
                source_id=source_id,
                research_space_id=research_space_id,
                run_id=normalized_run_id,
                resume_from_stage=normalized_resume_stage,
                stage="ingestion",
                stage_status=ingestion_status,
                overall_status="running",
                stage_error=(
                    errors[-1] if ingestion_status == "failed" and errors else None
                ),
            )
            run_cancelled = self._is_pipeline_run_cancelled(
                source_id=source_id,
                run_id=normalized_run_id,
            )

        normalized_source_type = (
            source_type.strip() if isinstance(source_type, str) else None
        )

        can_run_enrichment = ingestion_status == "completed" or (
            normalized_resume_stage in {"enrichment", "extraction", "graph"}
        )
        if should_run_enrichment and can_run_enrichment and not run_cancelled:
            enrichment_started_at = datetime.now(UTC)
            logger.info(
                "Pipeline stage started",
                extra={
                    "run_id": normalized_run_id,
                    "source_id": str(source_id),
                    "stage": "enrichment",
                    "ingestion_job_id": (
                        str(active_ingestion_job_id)
                        if active_ingestion_job_id is not None
                        else None
                    ),
                },
            )

            async def _run_enrichment_stage_with_compat() -> (
                ContentEnrichmentRunSummary
            ):
                if self._enrichment_stage_runner is not None:
                    return await self._enrichment_stage_runner(
                        limit=max(enrichment_limit, 1),
                        source_id=source_id,
                        ingestion_job_id=active_ingestion_job_id,
                        research_space_id=research_space_id,
                        source_type=normalized_source_type,
                        model_id=model_id,
                        pipeline_run_id=normalized_run_id,
                    )
                try:
                    return await self._enrichment.process_pending_documents(
                        limit=max(enrichment_limit, 1),
                        source_id=source_id,
                        ingestion_job_id=active_ingestion_job_id,
                        research_space_id=research_space_id,
                        source_type=normalized_source_type,
                        model_id=model_id,
                        pipeline_run_id=normalized_run_id,
                    )
                except TypeError as exc:
                    if "ingestion_job_id" not in str(exc):
                        raise
                    return await self._enrichment.process_pending_documents(
                        limit=max(enrichment_limit, 1),
                        source_id=source_id,
                        research_space_id=research_space_id,
                        source_type=normalized_source_type,
                        model_id=model_id,
                        pipeline_run_id=normalized_run_id,
                    )

            try:
                enrichment_summary = await _run_enrichment_stage_with_compat()
                enrichment_status = "completed"
                enrichment_processed = enrichment_summary.processed
                enrichment_enriched = enrichment_summary.enriched
                enrichment_failed = enrichment_summary.failed
                enrichment_ai_runs = (
                    enrichment_summary.ai_runs
                    if isinstance(getattr(enrichment_summary, "ai_runs", None), int)
                    else 0
                )
                enrichment_deterministic_runs = (
                    enrichment_summary.deterministic_runs
                    if isinstance(
                        getattr(enrichment_summary, "deterministic_runs", None),
                        int,
                    )
                    else 0
                )
                errors.extend(enrichment_summary.errors)
                enrichment_error_category = resolve_pipeline_error_category(
                    enrichment_summary.errors,
                )
                if enrichment_error_category is not None:
                    pipeline_error_category = enrichment_error_category
                if (
                    enrichment_error_category == "capacity"
                    and enrichment_summary.failed > 0
                ):
                    enrichment_status = "failed"
            except Exception as exc:  # noqa: BLE001 - surfaced in run summary
                enrichment_status = "failed"
                enrichment_error = f"enrichment:{exc!s}"
                errors.append(enrichment_error)
                stage_error_category = resolve_pipeline_error_category(
                    (enrichment_error,),
                )
                if stage_error_category is not None:
                    pipeline_error_category = stage_error_category
            enrichment_duration_ms = int(
                (datetime.now(UTC) - enrichment_started_at).total_seconds() * 1000,
            )
            logger.info(
                "Pipeline stage finished",
                extra={
                    "run_id": normalized_run_id,
                    "source_id": str(source_id),
                    "stage": "enrichment",
                    "stage_status": enrichment_status,
                    "duration_ms": enrichment_duration_ms,
                    "enrichment_processed": enrichment_processed,
                    "enrichment_enriched": enrichment_enriched,
                    "enrichment_failed": enrichment_failed,
                },
            )
            pipeline_run_job = self._persist_pipeline_stage_checkpoint(
                run_job=pipeline_run_job,
                source_id=source_id,
                research_space_id=research_space_id,
                run_id=normalized_run_id,
                resume_from_stage=normalized_resume_stage,
                stage="enrichment",
                stage_status=enrichment_status,
                overall_status="running",
                stage_error=(
                    errors[-1] if enrichment_status == "failed" and errors else None
                ),
            )
            run_cancelled = self._is_pipeline_run_cancelled(
                source_id=source_id,
                run_id=normalized_run_id,
            )

        can_run_extraction = enrichment_status == "completed" or (
            normalized_resume_stage in {"extraction", "graph"}
        )
        if should_run_extraction and can_run_extraction and not run_cancelled:
            configured_extraction_watchdog_timeout_seconds = (
                _read_positive_timeout_seconds(
                    _ENV_EXTRACTION_STAGE_WATCHDOG_TIMEOUT_SECONDS,
                    default_seconds=_DEFAULT_EXTRACTION_STAGE_WATCHDOG_TIMEOUT_SECONDS,
                )
            )
            raw_extraction_watchdog_timeout_override = os.getenv(
                _ENV_EXTRACTION_STAGE_WATCHDOG_TIMEOUT_SECONDS,
            )
            has_extraction_watchdog_timeout_override = False
            if (
                isinstance(raw_extraction_watchdog_timeout_override, str)
                and raw_extraction_watchdog_timeout_override.strip()
            ):
                try:
                    has_extraction_watchdog_timeout_override = (
                        float(raw_extraction_watchdog_timeout_override.strip()) > 0
                    )
                except ValueError:
                    has_extraction_watchdog_timeout_override = False
            entity_agent_timeout_seconds = _read_positive_timeout_seconds(
                _ENV_ENTITY_RECOGNITION_AGENT_TIMEOUT_SECONDS,
                default_seconds=_DEFAULT_ENTITY_RECOGNITION_AGENT_TIMEOUT_SECONDS,
            )
            entity_extraction_timeout_seconds = _read_positive_timeout_seconds(
                _ENV_ENTITY_RECOGNITION_EXTRACTION_STAGE_TIMEOUT_SECONDS,
                default_seconds=(
                    _DEFAULT_ENTITY_RECOGNITION_EXTRACTION_STAGE_TIMEOUT_SECONDS
                ),
            )
            entity_batch_max_concurrency = _read_positive_int(
                _ENV_ENTITY_RECOGNITION_BATCH_MAX_CONCURRENCY,
                default_value=_DEFAULT_ENTITY_RECOGNITION_BATCH_MAX_CONCURRENCY,
            )
            extraction_waves = max(
                (max(extraction_limit, 1) + entity_batch_max_concurrency - 1)
                // entity_batch_max_concurrency,
                1,
            )
            estimated_extraction_watchdog_timeout_seconds = float(
                extraction_waves,
            ) * (
                entity_agent_timeout_seconds
                + entity_extraction_timeout_seconds
                + _EXTRACTION_STAGE_TIMEOUT_OVERHEAD_SECONDS
            )
            extraction_watchdog_timeout_seconds = (
                configured_extraction_watchdog_timeout_seconds
            )
            if not has_extraction_watchdog_timeout_override:
                extraction_watchdog_timeout_seconds = max(
                    extraction_watchdog_timeout_seconds,
                    estimated_extraction_watchdog_timeout_seconds,
                )
            extraction_started_at = datetime.now(UTC)
            logger.info(
                "Pipeline stage started",
                extra={
                    "run_id": normalized_run_id,
                    "source_id": str(source_id),
                    "stage": "extraction",
                    "ingestion_job_id": (
                        str(active_ingestion_job_id)
                        if active_ingestion_job_id is not None
                        else None
                    ),
                    "configured_watchdog_timeout_seconds": (
                        configured_extraction_watchdog_timeout_seconds
                    ),
                    "estimated_watchdog_timeout_seconds": (
                        estimated_extraction_watchdog_timeout_seconds
                    ),
                    "entity_agent_timeout_seconds": entity_agent_timeout_seconds,
                    "entity_extraction_stage_timeout_seconds": (
                        entity_extraction_timeout_seconds
                    ),
                    "entity_batch_max_concurrency": entity_batch_max_concurrency,
                    "extraction_waves": extraction_waves,
                    "watchdog_timeout_override": (
                        raw_extraction_watchdog_timeout_override
                        if has_extraction_watchdog_timeout_override
                        else None
                    ),
                    "watchdog_timeout_seconds": extraction_watchdog_timeout_seconds,
                },
            )

            async def _run_extraction_stage_with_compat() -> (
                EntityRecognitionRunSummary
            ):
                if self._extraction_stage_runner is not None:
                    return await self._extraction_stage_runner(
                        limit=max(extraction_limit, 1),
                        source_id=source_id,
                        ingestion_job_id=active_ingestion_job_id,
                        research_space_id=research_space_id,
                        source_type=normalized_source_type,
                        model_id=model_id,
                        shadow_mode=shadow_mode,
                        pipeline_run_id=normalized_run_id,
                    )
                try:
                    return await self._extraction.process_pending_documents(
                        limit=max(extraction_limit, 1),
                        source_id=source_id,
                        ingestion_job_id=active_ingestion_job_id,
                        research_space_id=research_space_id,
                        source_type=normalized_source_type,
                        model_id=model_id,
                        shadow_mode=shadow_mode,
                        pipeline_run_id=normalized_run_id,
                    )
                except TypeError as exc:
                    if "ingestion_job_id" not in str(exc):
                        raise
                    return await self._extraction.process_pending_documents(
                        limit=max(extraction_limit, 1),
                        source_id=source_id,
                        research_space_id=research_space_id,
                        source_type=normalized_source_type,
                        model_id=model_id,
                        shadow_mode=shadow_mode,
                        pipeline_run_id=normalized_run_id,
                    )

            extraction_stage_error: str | None = None
            extraction_error_category: str | None = None
            try:
                extraction_summary = await asyncio.wait_for(
                    _run_extraction_stage_with_compat(),
                    timeout=extraction_watchdog_timeout_seconds,
                )
                extraction_status = "completed"
                extraction_processed = extraction_summary.processed
                extraction_extracted = extraction_summary.extracted
                extraction_failed = extraction_summary.failed
                extraction_persisted_relations_raw = getattr(
                    extraction_summary,
                    "persisted_relations_count",
                    0,
                )
                if isinstance(extraction_persisted_relations_raw, int):
                    extraction_persisted_relations = max(
                        extraction_persisted_relations_raw,
                        0,
                    )
                else:
                    extraction_persisted_relations = 0
                extraction_concept_members_created_raw = getattr(
                    extraction_summary,
                    "concept_members_created_count",
                    0,
                )
                if isinstance(extraction_concept_members_created_raw, int):
                    extraction_concept_members_created = max(
                        extraction_concept_members_created_raw,
                        0,
                    )
                else:
                    extraction_concept_members_created = 0
                extraction_concept_aliases_created_raw = getattr(
                    extraction_summary,
                    "concept_aliases_created_count",
                    0,
                )
                if isinstance(extraction_concept_aliases_created_raw, int):
                    extraction_concept_aliases_created = max(
                        extraction_concept_aliases_created_raw,
                        0,
                    )
                else:
                    extraction_concept_aliases_created = 0
                extraction_concept_decisions_proposed_raw = getattr(
                    extraction_summary,
                    "concept_decisions_proposed_count",
                    0,
                )
                if isinstance(extraction_concept_decisions_proposed_raw, int):
                    extraction_concept_decisions_proposed = max(
                        extraction_concept_decisions_proposed_raw,
                        0,
                    )
                else:
                    extraction_concept_decisions_proposed = 0
                total_persisted_relations = extraction_persisted_relations
                derived_graph_seed_entity_ids = (
                    self._extract_seed_entity_ids_from_extraction_summary(
                        extraction_summary,
                    )
                )
                extraction_graph_fallback_relations = (
                    extract_graph_fallback_relations_from_extraction_summary(
                        extraction_summary,
                    )
                )
                errors.extend(extraction_summary.errors)
                extraction_error_category = resolve_pipeline_error_category(
                    extraction_summary.errors,
                )
                if extraction_error_category is not None:
                    pipeline_error_category = extraction_error_category
                if extraction_error_category == "capacity" and extraction_failed > 0:
                    extraction_status = "failed"
                    extraction_stage_error = _first_matching_error(
                        extraction_summary.errors,
                        category=extraction_error_category,
                    )
                if extraction_processed > 0:
                    extraction_failure_ratio = extraction_failed / extraction_processed
                    if extraction_error_category != "capacity":
                        extraction_failure_ratio_threshold = (
                            _resolve_extraction_failure_ratio_threshold(
                                normalized_source_type,
                            )
                        )
                    if (
                        extraction_error_category != "capacity"
                        and extraction_failure_ratio_threshold is not None
                        and extraction_failure_ratio
                        > extraction_failure_ratio_threshold
                    ):
                        extraction_quality_gate_failed = True
                        extraction_stage_error = (
                            "extraction:quality_gate_failed:"
                            f"failed={extraction_failed}/processed={extraction_processed}:"
                            f"ratio={extraction_failure_ratio:.3f}:"
                            "threshold="
                            f"{extraction_failure_ratio_threshold:.3f}"
                        )
                        errors.append(extraction_stage_error)
                        logger.warning(
                            "Extraction quality gate failed for pipeline run",
                            extra={
                                "run_id": normalized_run_id,
                                "source_id": str(source_id),
                                "source_type": normalized_source_type,
                                "extraction_processed": extraction_processed,
                                "extraction_failed": extraction_failed,
                                "extraction_failure_ratio": extraction_failure_ratio,
                                "extraction_failure_ratio_threshold": (
                                    extraction_failure_ratio_threshold
                                ),
                            },
                        )
            except TimeoutError:
                extraction_status = "failed"
                timeout_error = (
                    "extraction:stage_timeout:"
                    f"{extraction_watchdog_timeout_seconds:.1f}s"
                )
                logger.exception(
                    "Pipeline extraction stage timed out for run_id=%s source_id=%s",
                    normalized_run_id,
                    source_id,
                )
                errors.append(timeout_error)
                extraction_stage_error = timeout_error
            except Exception as exc:  # noqa: BLE001 - surfaced in run summary
                extraction_status = "failed"
                extraction_stage_error = f"extraction:{exc!s}"
                errors.append(extraction_stage_error)
                extraction_error_category = resolve_pipeline_error_category(
                    (extraction_stage_error,),
                )
                if extraction_error_category is not None:
                    pipeline_error_category = extraction_error_category
            extraction_duration_ms = int(
                (datetime.now(UTC) - extraction_started_at).total_seconds() * 1000,
            )
            logger.info(
                "Pipeline stage finished",
                extra={
                    "run_id": normalized_run_id,
                    "source_id": str(source_id),
                    "stage": "extraction",
                    "stage_status": extraction_status,
                    "duration_ms": extraction_duration_ms,
                    "extraction_processed": extraction_processed,
                    "extraction_extracted": extraction_extracted,
                    "extraction_failed": extraction_failed,
                    "extraction_persisted_relations": extraction_persisted_relations,
                    "extraction_concept_members_created": (
                        extraction_concept_members_created
                    ),
                    "extraction_concept_aliases_created": (
                        extraction_concept_aliases_created
                    ),
                    "extraction_concept_decisions_proposed": (
                        extraction_concept_decisions_proposed
                    ),
                    "extraction_failure_ratio": extraction_failure_ratio,
                    "extraction_failure_ratio_threshold": (
                        extraction_failure_ratio_threshold
                    ),
                    "extraction_quality_gate_failed": extraction_quality_gate_failed,
                    "derived_graph_seed_entity_ids_count": len(
                        derived_graph_seed_entity_ids,
                    ),
                    "watchdog_timeout_seconds": extraction_watchdog_timeout_seconds,
                },
            )
            pipeline_run_job = self._persist_pipeline_run_progress(
                run_job=pipeline_run_job,
                source_id=source_id,
                research_space_id=research_space_id,
                run_id=normalized_run_id,
                resume_from_stage=normalized_resume_stage,
                progress_key="extraction_run",
                progress_payload={
                    "status": extraction_status,
                    "processed": extraction_processed,
                    "completed": extraction_extracted,
                    "failed": extraction_failed,
                    "persisted_relations": extraction_persisted_relations,
                    "concept_members_created": extraction_concept_members_created,
                    "concept_aliases_created": extraction_concept_aliases_created,
                    "concept_decisions_proposed": (
                        extraction_concept_decisions_proposed
                    ),
                    "quality_gate_failed": extraction_quality_gate_failed,
                    "failure_ratio": extraction_failure_ratio,
                    "failure_ratio_threshold": extraction_failure_ratio_threshold,
                    "last_error": extraction_stage_error,
                    "error_category": extraction_error_category,
                },
                overall_status="running",
            )
            pipeline_run_job = self._persist_pipeline_stage_checkpoint(
                run_job=pipeline_run_job,
                source_id=source_id,
                research_space_id=research_space_id,
                run_id=normalized_run_id,
                resume_from_stage=normalized_resume_stage,
                stage="extraction",
                stage_status=extraction_status,
                overall_status="running",
                stage_error=extraction_stage_error,
            )
            run_cancelled = self._is_pipeline_run_cancelled(
                source_id=source_id,
                run_id=normalized_run_id,
            )

        graph_stage_output = await self._run_graph_stage(
            graph_stage_input=_GraphStageInput(
                source_id=source_id,
                research_space_id=research_space_id,
                run_id=normalized_run_id,
                resume_from_stage=normalized_resume_stage,
                should_run_graph=should_run_graph,
                extraction_status=extraction_status,
                normalized_source_type=normalized_source_type,
                model_id=model_id,
                shadow_mode=shadow_mode,
                explicit_graph_seed_entity_ids=explicit_graph_seed_entity_ids,
                derived_graph_seed_entity_ids=derived_graph_seed_entity_ids,
                extraction_graph_fallback_relations=(
                    extraction_graph_fallback_relations
                ),
                extraction_processed=extraction_processed,
                extraction_extracted=extraction_extracted,
                extraction_failed=extraction_failed,
                extraction_persisted_relations=extraction_persisted_relations,
                extraction_concept_members_created=(extraction_concept_members_created),
                extraction_concept_aliases_created=(extraction_concept_aliases_created),
                extraction_concept_decisions_proposed=(
                    extraction_concept_decisions_proposed
                ),
                total_persisted_relations=total_persisted_relations,
                graph_status=graph_status,
                errors=errors,
                pipeline_error_category=pipeline_error_category,
                run_cancelled=run_cancelled,
                pipeline_run_job=pipeline_run_job,
                graph_relation_types=graph_relation_types,
                graph_max_depth=graph_max_depth,
            ),
        )
        inferred_graph_seed_entity_ids = (
            graph_stage_output.inferred_graph_seed_entity_ids
        )
        active_graph_seed_entity_ids = graph_stage_output.active_graph_seed_entity_ids
        graph_seed_mode = graph_stage_output.graph_seed_mode
        graph_seed_limit = graph_stage_output.graph_seed_limit
        graph_requested = graph_stage_output.graph_requested
        graph_processed = graph_stage_output.graph_processed
        graph_stage_persisted_relations = (
            graph_stage_output.graph_stage_persisted_relations
        )
        total_persisted_relations = graph_stage_output.total_persisted_relations
        graph_status = graph_stage_output.graph_status
        pipeline_error_category = graph_stage_output.pipeline_error_category
        run_cancelled = graph_stage_output.run_cancelled
        pipeline_run_job = graph_stage_output.pipeline_run_job

        if run_cancelled and "pipeline:cancelled" not in errors:
            errors.append("pipeline:cancelled")

        completed_at = datetime.now(UTC)
        pipeline_error_category = (
            resolve_pipeline_error_category(errors) or pipeline_error_category
        )
        run_status: Literal["completed", "failed", "cancelled"] = "completed"
        if run_cancelled:
            run_status = "cancelled"
        elif (
            any(
                stage == "failed"
                for stage in (
                    ingestion_status,
                    enrichment_status,
                    extraction_status,
                    graph_status,
                )
            )
            or extraction_quality_gate_failed
        ):
            run_status = "failed"
        pipeline_run_job = self._finalize_pipeline_run_checkpoint(
            run_job=pipeline_run_job,
            source_id=source_id,
            research_space_id=research_space_id,
            run_id=normalized_run_id,
            resume_from_stage=normalized_resume_stage,
            run_status=run_status,
            errors=tuple(errors),
            created_publications=created_publications,
            updated_publications=updated_publications,
            extraction_extracted=extraction_extracted,
            graph_persisted_relations=total_persisted_relations,
        )
        logger.info(
            "Pipeline run finished",
            extra={
                "run_id": normalized_run_id,
                "source_id": str(source_id),
                "research_space_id": str(research_space_id),
                "run_status": run_status,
                "duration_ms": int(
                    (datetime.now(UTC) - started_at).total_seconds() * 1000,
                ),
                "ingestion_status": ingestion_status,
                "enrichment_status": enrichment_status,
                "extraction_status": extraction_status,
                "graph_status": graph_status,
                "extraction_quality_gate_failed": extraction_quality_gate_failed,
                "extraction_failure_ratio": extraction_failure_ratio,
                "extraction_failure_ratio_threshold": (
                    extraction_failure_ratio_threshold
                ),
                "error_count": len(errors),
            },
        )

        return PipelineRunSummary(
            run_id=normalized_run_id,
            resume_from_stage=normalized_resume_stage,
            source_id=source_id,
            research_space_id=research_space_id,
            started_at=started_at,
            completed_at=completed_at,
            status=run_status,
            ingestion_status=ingestion_status,
            enrichment_status=enrichment_status,
            extraction_status=extraction_status,
            graph_status=graph_status,
            fetched_records=fetched_records,
            parsed_publications=parsed_publications,
            created_publications=created_publications,
            updated_publications=updated_publications,
            enrichment_processed=enrichment_processed,
            enrichment_enriched=enrichment_enriched,
            enrichment_failed=enrichment_failed,
            extraction_processed=extraction_processed,
            extraction_extracted=extraction_extracted,
            extraction_failed=extraction_failed,
            graph_requested=graph_requested,
            graph_processed=graph_processed,
            graph_persisted_relations=total_persisted_relations,
            executed_query=executed_query,
            errors=tuple(errors),
            metadata={
                "run_id": normalized_run_id,
                "resume_from_stage": normalized_resume_stage,
                "pipeline_run_checkpoint_id": (
                    str(pipeline_run_job.id) if pipeline_run_job is not None else None
                ),
                "query_generation_execution_mode": query_generation_execution_mode,
                "query_generation_fallback_reason": query_generation_fallback_reason,
                "ingestion_job_id": (
                    str(active_ingestion_job_id)
                    if active_ingestion_job_id is not None
                    else None
                ),
                "enrichment_ai_runs": enrichment_ai_runs,
                "enrichment_deterministic_runs": enrichment_deterministic_runs,
                "ingestion_status": ingestion_status,
                "enrichment_status": enrichment_status,
                "extraction_status": extraction_status,
                "graph_status": graph_status,
                "extraction_persisted_relations": extraction_persisted_relations,
                "extraction_concept_members_created": (
                    extraction_concept_members_created
                ),
                "extraction_concept_aliases_created": (
                    extraction_concept_aliases_created
                ),
                "extraction_concept_decisions_proposed": (
                    extraction_concept_decisions_proposed
                ),
                "graph_stage_persisted_relations": (graph_stage_persisted_relations),
                "total_persisted_relations": total_persisted_relations,
                "extraction_quality_gate_failed": extraction_quality_gate_failed,
                "extraction_failure_ratio": extraction_failure_ratio,
                "extraction_failure_ratio_threshold": (
                    extraction_failure_ratio_threshold
                ),
                "error_category": pipeline_error_category,
                "graph_seed_mode": graph_seed_mode,
                "graph_explicit_seed_count": len(explicit_graph_seed_entity_ids),
                "graph_derived_seed_count": len(derived_graph_seed_entity_ids),
                "graph_inferred_seed_count": len(inferred_graph_seed_entity_ids),
                "graph_active_seed_ids": list(active_graph_seed_entity_ids),
                "graph_seed_limit": graph_seed_limit,
                "graph_extraction_fallback_seed_count": len(
                    extraction_graph_fallback_relations,
                ),
                "graph_extraction_fallback_relation_count": sum(
                    len(relations)
                    for relations in extraction_graph_fallback_relations.values()
                ),
            },
        )
