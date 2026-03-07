"""Graph-stage helper mixin for unified pipeline orchestration."""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from src.application.services._pipeline_failure_classification import (
    resolve_pipeline_error_category,
)
from src.application.services._pipeline_orchestration_graph_fallback_helpers import (
    resolve_graph_seed_limit,
)

if TYPE_CHECKING:
    from uuid import UUID

    from src.application.agents.services.graph_connection_service import (
        GraphConnectionOutcome,
    )
    from src.application.services._pipeline_orchestration_contracts import (
        PipelineStageName,
        PipelineStageStatus,
    )
    from src.application.services._pipeline_orchestration_execution_protocols import (
        _PipelineExecutionSelf,
    )
    from src.domain.agents.contracts.graph_connection import ProposedRelation
    from src.domain.entities.ingestion_job import IngestionJob

logger = logging.getLogger(__name__)

_ENV_GRAPH_SEED_INFERENCE_TIMEOUT_SECONDS = (
    "MED13_PIPELINE_GRAPH_SEED_INFERENCE_TIMEOUT_SECONDS"
)
_DEFAULT_GRAPH_SEED_INFERENCE_TIMEOUT_SECONDS = 120.0
_ENV_GRAPH_STAGE_MAX_CONCURRENCY = "MED13_PIPELINE_GRAPH_STAGE_MAX_CONCURRENCY"
_DEFAULT_GRAPH_STAGE_MAX_CONCURRENCY = 2
_ENV_GRAPH_STAGE_SEED_TIMEOUT_SECONDS = (
    "MED13_PIPELINE_GRAPH_STAGE_SEED_TIMEOUT_SECONDS"
)
_DEFAULT_GRAPH_STAGE_SEED_TIMEOUT_SECONDS = 180.0
_ENV_GRAPH_MAX_SEEDS_PER_RUN = "MED13_GRAPH_MAX_SEEDS_PER_RUN"
_DEFAULT_GRAPH_MAX_SEEDS_PER_RUN = 5


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


@dataclass(slots=True)
class _GraphStageInput:
    source_id: UUID
    research_space_id: UUID
    run_id: str
    resume_from_stage: PipelineStageName | None
    should_run_graph: bool
    extraction_status: PipelineStageStatus
    normalized_source_type: str | None
    model_id: str | None
    shadow_mode: bool | None
    explicit_graph_seed_entity_ids: list[str]
    derived_graph_seed_entity_ids: list[str]
    extraction_graph_fallback_relations: dict[str, tuple[ProposedRelation, ...]]
    extraction_processed: int
    extraction_extracted: int
    extraction_failed: int
    extraction_persisted_relations: int
    extraction_concept_members_created: int
    extraction_concept_aliases_created: int
    extraction_concept_decisions_proposed: int
    total_persisted_relations: int
    graph_status: PipelineStageStatus
    errors: list[str]
    pipeline_error_category: str | None
    run_cancelled: bool
    pipeline_run_job: IngestionJob | None
    graph_relation_types: list[str] | None
    graph_max_depth: int


@dataclass(slots=True)
class _GraphStageOutput:
    active_graph_seed_entity_ids: list[str]
    inferred_graph_seed_entity_ids: list[str]
    graph_seed_mode: str
    graph_seed_limit: int
    graph_requested: int
    graph_processed: int
    graph_stage_persisted_relations: int
    total_persisted_relations: int
    graph_status: PipelineStageStatus
    pipeline_error_category: str | None
    run_cancelled: bool
    pipeline_run_job: IngestionJob | None


class _PipelineOrchestrationGraphStageHelpers:
    """Helpers for graph seed inference and graph discovery execution."""

    async def _run_graph_stage(  # noqa: C901, PLR0912, PLR0915
        self: _PipelineExecutionSelf,
        *,
        graph_stage_input: _GraphStageInput,
    ) -> _GraphStageOutput:
        errors = graph_stage_input.errors
        run_cancelled = graph_stage_input.run_cancelled
        pipeline_error_category = graph_stage_input.pipeline_error_category
        pipeline_run_job = graph_stage_input.pipeline_run_job
        graph_status = graph_stage_input.graph_status
        graph_processed = 0
        graph_stage_persisted_relations = 0
        total_persisted_relations = graph_stage_input.total_persisted_relations
        inferred_graph_seed_entity_ids: list[str] = []
        active_graph_seed_entity_ids = list(
            graph_stage_input.explicit_graph_seed_entity_ids,
        )
        graph_seed_mode = (
            "explicit" if graph_stage_input.explicit_graph_seed_entity_ids else "none"
        )

        if (
            not run_cancelled
            and not graph_stage_input.explicit_graph_seed_entity_ids
            and not graph_stage_input.derived_graph_seed_entity_ids
        ):
            seed_inference_timeout_seconds = _read_positive_timeout_seconds(
                _ENV_GRAPH_SEED_INFERENCE_TIMEOUT_SECONDS,
                default_seconds=_DEFAULT_GRAPH_SEED_INFERENCE_TIMEOUT_SECONDS,
            )
            try:
                inferred_graph_seed_entity_ids = await asyncio.wait_for(
                    self._infer_seed_entity_ids_with_context(
                        source_id=graph_stage_input.source_id,
                        research_space_id=graph_stage_input.research_space_id,
                        source_type=graph_stage_input.normalized_source_type,
                        model_id=graph_stage_input.model_id,
                    ),
                    timeout=seed_inference_timeout_seconds,
                )
            except TimeoutError:
                graph_seed_inference_error = (
                    "graph_seed_inference:stage_timeout:"
                    f"{seed_inference_timeout_seconds:.1f}s"
                )
                errors.append(graph_seed_inference_error)
                logger.warning(
                    "Graph seed inference timed out",
                    extra={
                        "run_id": graph_stage_input.run_id,
                        "source_id": str(graph_stage_input.source_id),
                        "timeout_seconds": seed_inference_timeout_seconds,
                    },
                )
            except Exception as exc:  # noqa: BLE001 - surfaced in run summary
                graph_seed_inference_error = f"graph_seed_inference:{exc!s}"
                errors.append(graph_seed_inference_error)
                stage_error_category = resolve_pipeline_error_category(
                    (graph_seed_inference_error,),
                )
                if stage_error_category is not None:
                    pipeline_error_category = stage_error_category
                logger.warning(
                    "Graph seed inference failed",
                    extra={
                        "run_id": graph_stage_input.run_id,
                        "source_id": str(graph_stage_input.source_id),
                        "error": str(exc),
                    },
                )

        if (
            not graph_stage_input.explicit_graph_seed_entity_ids
            and graph_stage_input.derived_graph_seed_entity_ids
        ):
            active_graph_seed_entity_ids = list(
                graph_stage_input.derived_graph_seed_entity_ids,
            )
            graph_seed_mode = "derived_from_extraction"
        elif (
            not graph_stage_input.explicit_graph_seed_entity_ids
            and inferred_graph_seed_entity_ids
        ):
            active_graph_seed_entity_ids = list(inferred_graph_seed_entity_ids)
            graph_seed_mode = "ai_inferred_from_context"
        else:
            active_graph_seed_entity_ids = list(
                graph_stage_input.explicit_graph_seed_entity_ids,
            )

        graph_seed_limit = resolve_graph_seed_limit(
            env_name=_ENV_GRAPH_MAX_SEEDS_PER_RUN,
            default=_DEFAULT_GRAPH_MAX_SEEDS_PER_RUN,
        )
        if len(active_graph_seed_entity_ids) > graph_seed_limit:
            active_graph_seed_entity_ids = active_graph_seed_entity_ids[
                :graph_seed_limit
            ]
        graph_requested = len(active_graph_seed_entity_ids)

        can_run_graph = graph_stage_input.extraction_status == "completed" or (
            graph_stage_input.resume_from_stage == "graph"
        )
        if (
            graph_stage_input.should_run_graph
            and can_run_graph
            and graph_requested > 0
            and self._graph is not None
            and not run_cancelled
        ):
            graph_started_at = datetime.now(UTC)
            graph_max_concurrency = _read_positive_int(
                _ENV_GRAPH_STAGE_MAX_CONCURRENCY,
                default_value=_DEFAULT_GRAPH_STAGE_MAX_CONCURRENCY,
            )
            graph_seed_timeout_seconds = _read_positive_timeout_seconds(
                _ENV_GRAPH_STAGE_SEED_TIMEOUT_SECONDS,
                default_seconds=_DEFAULT_GRAPH_STAGE_SEED_TIMEOUT_SECONDS,
            )
            logger.info(
                "Pipeline stage started",
                extra={
                    "run_id": graph_stage_input.run_id,
                    "source_id": str(graph_stage_input.source_id),
                    "stage": "graph",
                    "requested_seed_count": graph_requested,
                    "max_concurrency": graph_max_concurrency,
                    "seed_timeout_seconds": graph_seed_timeout_seconds,
                },
            )
            normalized_source = (
                graph_stage_input.normalized_source_type
                if graph_stage_input.normalized_source_type
                else "clinvar"
            )
            graph_status = "completed"
            graph_completed_count = 0
            graph_semaphore = asyncio.Semaphore(graph_max_concurrency)
            pipeline_run_job = self._persist_pipeline_run_progress(
                run_job=pipeline_run_job,
                source_id=graph_stage_input.source_id,
                research_space_id=graph_stage_input.research_space_id,
                run_id=graph_stage_input.run_id,
                resume_from_stage=graph_stage_input.resume_from_stage,
                progress_key="graph_progress",
                progress_payload={
                    "status": "running",
                    "requested": graph_requested,
                    "completed": graph_completed_count,
                    "processed": graph_processed,
                    "extraction_processed": graph_stage_input.extraction_processed,
                    "extraction_completed": graph_stage_input.extraction_extracted,
                    "extraction_failed": graph_stage_input.extraction_failed,
                    "persisted_relations": total_persisted_relations,
                    "extraction_persisted_relations": (
                        graph_stage_input.extraction_persisted_relations
                    ),
                    "extraction_concept_members_created": (
                        graph_stage_input.extraction_concept_members_created
                    ),
                    "extraction_concept_aliases_created": (
                        graph_stage_input.extraction_concept_aliases_created
                    ),
                    "extraction_concept_decisions_proposed": (
                        graph_stage_input.extraction_concept_decisions_proposed
                    ),
                    "graph_stage_persisted_relations": (
                        graph_stage_persisted_relations
                    ),
                    "max_concurrency": graph_max_concurrency,
                    "last_seed_entity_id": None,
                    "last_error": None,
                },
                overall_status="running",
            )

            async def _discover_seed(  # noqa: C901
                seed_entity_id: str,
            ) -> tuple[str, int, tuple[str, ...], str | None, bool]:
                async with graph_semaphore:
                    if self._is_pipeline_run_cancelled(
                        source_id=graph_stage_input.source_id,
                        run_id=graph_stage_input.run_id,
                    ):
                        return seed_entity_id, 0, (), None, True
                    fallback_relations = (
                        graph_stage_input.extraction_graph_fallback_relations.get(
                            seed_entity_id,
                            (),
                        )
                    )

                    try:

                        async def _run_graph_discovery() -> (  # noqa: C901
                            GraphConnectionOutcome
                        ):
                            if self._graph_seed_runner is not None:
                                return await self._graph_seed_runner(
                                    source_id=str(graph_stage_input.source_id),
                                    research_space_id=str(
                                        graph_stage_input.research_space_id,
                                    ),
                                    seed_entity_id=seed_entity_id,
                                    source_type=normalized_source,
                                    model_id=graph_stage_input.model_id,
                                    relation_types=(
                                        graph_stage_input.graph_relation_types
                                    ),
                                    max_depth=graph_stage_input.graph_max_depth,
                                    shadow_mode=graph_stage_input.shadow_mode,
                                    pipeline_run_id=graph_stage_input.run_id,
                                    fallback_relations=fallback_relations,
                                )
                            graph_service = self._graph
                            if graph_service is None:
                                msg = "graph service unavailable"
                                raise RuntimeError(msg)  # noqa: TRY301

                            async def _call_graph_discovery(  # noqa: PLR0913
                                *,
                                include_source_id: bool,
                                include_fallback_relations: bool,
                            ) -> GraphConnectionOutcome:
                                if include_source_id and include_fallback_relations:
                                    return await graph_service.discover_connections_for_seed(
                                        research_space_id=str(
                                            graph_stage_input.research_space_id,
                                        ),
                                        seed_entity_id=seed_entity_id,
                                        source_id=str(graph_stage_input.source_id),
                                        source_type=normalized_source,
                                        model_id=graph_stage_input.model_id,
                                        relation_types=(
                                            graph_stage_input.graph_relation_types
                                        ),
                                        max_depth=graph_stage_input.graph_max_depth,
                                        shadow_mode=graph_stage_input.shadow_mode,
                                        pipeline_run_id=graph_stage_input.run_id,
                                        fallback_relations=fallback_relations,
                                    )
                                if include_source_id and not include_fallback_relations:
                                    return await graph_service.discover_connections_for_seed(
                                        research_space_id=str(
                                            graph_stage_input.research_space_id,
                                        ),
                                        seed_entity_id=seed_entity_id,
                                        source_id=str(graph_stage_input.source_id),
                                        source_type=normalized_source,
                                        model_id=graph_stage_input.model_id,
                                        relation_types=(
                                            graph_stage_input.graph_relation_types
                                        ),
                                        max_depth=graph_stage_input.graph_max_depth,
                                        shadow_mode=graph_stage_input.shadow_mode,
                                        pipeline_run_id=graph_stage_input.run_id,
                                    )
                                if not include_source_id and include_fallback_relations:
                                    return await graph_service.discover_connections_for_seed(
                                        research_space_id=str(
                                            graph_stage_input.research_space_id,
                                        ),
                                        seed_entity_id=seed_entity_id,
                                        source_type=normalized_source,
                                        model_id=graph_stage_input.model_id,
                                        relation_types=(
                                            graph_stage_input.graph_relation_types
                                        ),
                                        max_depth=graph_stage_input.graph_max_depth,
                                        shadow_mode=graph_stage_input.shadow_mode,
                                        pipeline_run_id=graph_stage_input.run_id,
                                        fallback_relations=fallback_relations,
                                    )
                                return (
                                    await graph_service.discover_connections_for_seed(
                                        research_space_id=str(
                                            graph_stage_input.research_space_id,
                                        ),
                                        seed_entity_id=seed_entity_id,
                                        source_type=normalized_source,
                                        model_id=graph_stage_input.model_id,
                                        relation_types=(
                                            graph_stage_input.graph_relation_types
                                        ),
                                        max_depth=graph_stage_input.graph_max_depth,
                                        shadow_mode=graph_stage_input.shadow_mode,
                                        pipeline_run_id=graph_stage_input.run_id,
                                    )
                                )

                            include_source_id = True
                            include_fallback_relations = True
                            while True:
                                try:
                                    return await _call_graph_discovery(
                                        include_source_id=include_source_id,
                                        include_fallback_relations=(
                                            include_fallback_relations
                                        ),
                                    )
                                except TypeError as exc:
                                    fallback_message = str(exc)
                                    removed_unsupported_key = False
                                    if (
                                        "fallback_relations" in fallback_message
                                        and include_fallback_relations
                                    ):
                                        include_fallback_relations = False
                                        removed_unsupported_key = True
                                    if (
                                        "source_id" in fallback_message
                                        and include_source_id
                                    ):
                                        include_source_id = False
                                        removed_unsupported_key = True
                                    if not removed_unsupported_key:
                                        raise

                        graph_outcome = await asyncio.wait_for(
                            _run_graph_discovery(),
                            timeout=graph_seed_timeout_seconds,
                        )
                        return (  # noqa: TRY300
                            seed_entity_id,
                            graph_outcome.persisted_relations_count,
                            graph_outcome.errors,
                            None,
                            False,
                        )
                    except TimeoutError:
                        return (
                            seed_entity_id,
                            0,
                            (),
                            f"seed_timeout:{graph_seed_timeout_seconds:.1f}s",
                            False,
                        )
                    except Exception as exc:  # noqa: BLE001 - surfaced in run summary
                        return seed_entity_id, 0, (), str(exc), False

            graph_tasks = [
                asyncio.create_task(_discover_seed(seed_entity_id))
                for seed_entity_id in active_graph_seed_entity_ids
            ]
            for completed_task in asyncio.as_completed(graph_tasks):
                (
                    completed_seed_id,
                    persisted_relations_count,
                    outcome_errors,
                    stage_error,
                    was_cancelled,
                ) = await completed_task
                graph_completed_count += 1
                if was_cancelled:
                    run_cancelled = True
                    graph_status = "skipped"
                elif stage_error is not None:
                    graph_status = "failed"
                    errors.append(f"graph:{completed_seed_id}:{stage_error}")
                    stage_error_category = resolve_pipeline_error_category(
                        (stage_error,),
                    )
                    if stage_error_category is not None:
                        pipeline_error_category = stage_error_category
                else:
                    graph_processed += 1
                    graph_stage_persisted_relations += persisted_relations_count
                    total_persisted_relations += persisted_relations_count
                    errors.extend(outcome_errors)
                    outcome_error_category = resolve_pipeline_error_category(
                        outcome_errors,
                    )
                    if outcome_error_category is not None:
                        pipeline_error_category = outcome_error_category
                    if outcome_error_category == "capacity":
                        graph_status = "failed"
                pipeline_run_job = self._persist_pipeline_run_progress(
                    run_job=pipeline_run_job,
                    source_id=graph_stage_input.source_id,
                    research_space_id=graph_stage_input.research_space_id,
                    run_id=graph_stage_input.run_id,
                    resume_from_stage=graph_stage_input.resume_from_stage,
                    progress_key="graph_progress",
                    progress_payload={
                        "status": "running",
                        "requested": graph_requested,
                        "completed": graph_completed_count,
                        "processed": graph_processed,
                        "extraction_processed": graph_stage_input.extraction_processed,
                        "extraction_completed": (
                            graph_stage_input.extraction_extracted
                        ),
                        "extraction_failed": graph_stage_input.extraction_failed,
                        "persisted_relations": total_persisted_relations,
                        "extraction_persisted_relations": (
                            graph_stage_input.extraction_persisted_relations
                        ),
                        "extraction_concept_members_created": (
                            graph_stage_input.extraction_concept_members_created
                        ),
                        "extraction_concept_aliases_created": (
                            graph_stage_input.extraction_concept_aliases_created
                        ),
                        "extraction_concept_decisions_proposed": (
                            graph_stage_input.extraction_concept_decisions_proposed
                        ),
                        "graph_stage_persisted_relations": (
                            graph_stage_persisted_relations
                        ),
                        "max_concurrency": graph_max_concurrency,
                        "last_seed_entity_id": completed_seed_id,
                        "last_error": stage_error,
                    },
                    overall_status="running",
                )
                if run_cancelled:
                    for graph_task in graph_tasks:
                        if not graph_task.done():
                            graph_task.cancel()
                    await asyncio.gather(*graph_tasks, return_exceptions=True)
                    break
            graph_duration_ms = int(
                (datetime.now(UTC) - graph_started_at).total_seconds() * 1000,
            )
            pipeline_run_job = self._persist_pipeline_run_progress(
                run_job=pipeline_run_job,
                source_id=graph_stage_input.source_id,
                research_space_id=graph_stage_input.research_space_id,
                run_id=graph_stage_input.run_id,
                resume_from_stage=graph_stage_input.resume_from_stage,
                progress_key="graph_progress",
                progress_payload={
                    "status": graph_status,
                    "requested": graph_requested,
                    "completed": graph_completed_count,
                    "processed": graph_processed,
                    "extraction_processed": graph_stage_input.extraction_processed,
                    "extraction_completed": graph_stage_input.extraction_extracted,
                    "extraction_failed": graph_stage_input.extraction_failed,
                    "persisted_relations": total_persisted_relations,
                    "extraction_persisted_relations": (
                        graph_stage_input.extraction_persisted_relations
                    ),
                    "extraction_concept_members_created": (
                        graph_stage_input.extraction_concept_members_created
                    ),
                    "extraction_concept_aliases_created": (
                        graph_stage_input.extraction_concept_aliases_created
                    ),
                    "extraction_concept_decisions_proposed": (
                        graph_stage_input.extraction_concept_decisions_proposed
                    ),
                    "graph_stage_persisted_relations": (
                        graph_stage_persisted_relations
                    ),
                    "max_concurrency": graph_max_concurrency,
                },
                overall_status="running",
            )
            logger.info(
                "Pipeline stage finished",
                extra={
                    "run_id": graph_stage_input.run_id,
                    "source_id": str(graph_stage_input.source_id),
                    "stage": "graph",
                    "stage_status": graph_status,
                    "duration_ms": graph_duration_ms,
                    "graph_requested": graph_requested,
                    "graph_processed": graph_processed,
                    "graph_stage_persisted_relations": graph_stage_persisted_relations,
                    "total_persisted_relations": total_persisted_relations,
                },
            )
        elif (
            graph_stage_input.should_run_graph and can_run_graph and graph_requested > 0
        ):
            graph_status = "failed"
            errors.append("graph:service_unavailable")

        if graph_stage_input.should_run_graph and can_run_graph and graph_requested > 0:
            pipeline_run_job = self._persist_pipeline_stage_checkpoint(
                run_job=pipeline_run_job,
                source_id=graph_stage_input.source_id,
                research_space_id=graph_stage_input.research_space_id,
                run_id=graph_stage_input.run_id,
                resume_from_stage=graph_stage_input.resume_from_stage,
                stage="graph",
                stage_status=graph_status,
                overall_status="running",
                stage_error=errors[-1] if graph_status == "failed" and errors else None,
            )

        return _GraphStageOutput(
            active_graph_seed_entity_ids=active_graph_seed_entity_ids,
            inferred_graph_seed_entity_ids=inferred_graph_seed_entity_ids,
            graph_seed_mode=graph_seed_mode,
            graph_seed_limit=graph_seed_limit,
            graph_requested=graph_requested,
            graph_processed=graph_processed,
            graph_stage_persisted_relations=graph_stage_persisted_relations,
            total_persisted_relations=total_persisted_relations,
            graph_status=graph_status,
            pipeline_error_category=pipeline_error_category,
            run_cancelled=run_cancelled,
            pipeline_run_job=pipeline_run_job,
        )


__all__ = [
    "_GraphStageInput",
    "_GraphStageOutput",
    "_PipelineOrchestrationGraphStageHelpers",
]
