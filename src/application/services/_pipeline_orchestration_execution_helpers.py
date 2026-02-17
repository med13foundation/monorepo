"""Execution helpers for unified pipeline orchestration."""

# mypy: disable-error-code="misc"

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Literal

from src.application.services._pipeline_orchestration_contracts import (
    PipelineRunSummary,
    PipelineStageName,
    PipelineStageStatus,
)
from src.application.services._pipeline_orchestration_graph_fallback_helpers import (
    extract_graph_fallback_relations_from_extraction_summary,
    resolve_graph_seed_limit,
    resolve_latest_ingestion_job_id,
)
from src.application.services._pipeline_orchestration_seed_helpers import (
    _PipelineOrchestrationContextSeedHelpers,
)

if TYPE_CHECKING:
    from uuid import UUID

    from src.application.services._pipeline_orchestration_execution_protocols import (
        _PipelineExecutionSelf,
    )
    from src.domain.agents.contracts.graph_connection import ProposedRelation


class _PipelineOrchestrationExecutionHelpers(
    _PipelineOrchestrationContextSeedHelpers,
):
    """Execution-stage helpers for unified pipeline runs."""

    _ENV_GRAPH_MAX_SEEDS_PER_RUN = "MED13_GRAPH_MAX_SEEDS_PER_RUN"
    _DEFAULT_GRAPH_MAX_SEEDS_PER_RUN = 5

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
        graph_seed_entity_ids: list[str] | None = None,
        graph_max_depth: int = 2,
        graph_relation_types: list[str] | None = None,
    ) -> PipelineRunSummary:
        started_at = datetime.now(UTC)
        normalized_run_id = self._resolve_run_id(run_id)
        normalized_resume_stage = self._resolve_resume_stage(resume_from_stage)
        errors: list[str] = []

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
        graph_persisted_relations = 0
        active_ingestion_job_id: UUID | None = None
        pipeline_run_job = self._start_or_resume_pipeline_run(
            source_id=source_id,
            research_space_id=research_space_id,
            run_id=normalized_run_id,
            resume_from_stage=normalized_resume_stage,
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

        if should_run_ingestion:
            try:
                ingestion_summary = await self._ingestion.trigger_ingestion(source_id)
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
                active_ingestion_job_id = resolve_latest_ingestion_job_id(
                    ingestion_service=self._ingestion,
                    source_id=source_id,
                )
            except Exception as exc:  # noqa: BLE001 - surfaced in run summary
                ingestion_status = "failed"
                errors.append(f"ingestion:{exc!s}")
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

        normalized_source_type = (
            source_type.strip() if isinstance(source_type, str) else None
        )

        can_run_enrichment = ingestion_status == "completed" or (
            normalized_resume_stage in {"enrichment", "extraction", "graph"}
        )
        if should_run_enrichment and can_run_enrichment:
            try:
                try:
                    enrichment_summary = (
                        await self._enrichment.process_pending_documents(
                            limit=max(enrichment_limit, 1),
                            source_id=source_id,
                            ingestion_job_id=active_ingestion_job_id,
                            research_space_id=research_space_id,
                            source_type=normalized_source_type,
                            model_id=model_id,
                            pipeline_run_id=normalized_run_id,
                        )
                    )
                except TypeError as exc:
                    if "ingestion_job_id" not in str(exc):
                        raise
                    enrichment_summary = (
                        await self._enrichment.process_pending_documents(
                            limit=max(enrichment_limit, 1),
                            source_id=source_id,
                            research_space_id=research_space_id,
                            source_type=normalized_source_type,
                            model_id=model_id,
                            pipeline_run_id=normalized_run_id,
                        )
                    )
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
            except Exception as exc:  # noqa: BLE001 - surfaced in run summary
                enrichment_status = "failed"
                errors.append(f"enrichment:{exc!s}")
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

        can_run_extraction = enrichment_status == "completed" or (
            normalized_resume_stage in {"extraction", "graph"}
        )
        if should_run_extraction and can_run_extraction:
            try:
                try:
                    extraction_summary = (
                        await self._extraction.process_pending_documents(
                            limit=max(extraction_limit, 1),
                            source_id=source_id,
                            ingestion_job_id=active_ingestion_job_id,
                            research_space_id=research_space_id,
                            source_type=normalized_source_type,
                            model_id=model_id,
                            shadow_mode=shadow_mode,
                            pipeline_run_id=normalized_run_id,
                        )
                    )
                except TypeError as exc:
                    if "ingestion_job_id" not in str(exc):
                        raise
                    extraction_summary = (
                        await self._extraction.process_pending_documents(
                            limit=max(extraction_limit, 1),
                            source_id=source_id,
                            research_space_id=research_space_id,
                            source_type=normalized_source_type,
                            model_id=model_id,
                            shadow_mode=shadow_mode,
                            pipeline_run_id=normalized_run_id,
                        )
                    )
                extraction_status = "completed"
                extraction_processed = extraction_summary.processed
                extraction_extracted = extraction_summary.extracted
                extraction_failed = extraction_summary.failed
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
            except Exception as exc:  # noqa: BLE001 - surfaced in run summary
                extraction_status = "failed"
                errors.append(f"extraction:{exc!s}")
            pipeline_run_job = self._persist_pipeline_stage_checkpoint(
                run_job=pipeline_run_job,
                source_id=source_id,
                research_space_id=research_space_id,
                run_id=normalized_run_id,
                resume_from_stage=normalized_resume_stage,
                stage="extraction",
                stage_status=extraction_status,
                overall_status="running",
                stage_error=(
                    errors[-1] if extraction_status == "failed" and errors else None
                ),
            )

        if not explicit_graph_seed_entity_ids and not derived_graph_seed_entity_ids:
            inferred_graph_seed_entity_ids = (
                await self._infer_seed_entity_ids_with_context(
                    source_id=source_id,
                    research_space_id=research_space_id,
                    source_type=normalized_source_type,
                    model_id=model_id,
                )
            )
        if not explicit_graph_seed_entity_ids and derived_graph_seed_entity_ids:
            active_graph_seed_entity_ids = list(derived_graph_seed_entity_ids)
            graph_seed_mode = "derived_from_extraction"
        elif not explicit_graph_seed_entity_ids and inferred_graph_seed_entity_ids:
            active_graph_seed_entity_ids = list(inferred_graph_seed_entity_ids)
            graph_seed_mode = "ai_inferred_from_context"
        else:
            active_graph_seed_entity_ids = list(explicit_graph_seed_entity_ids)
        graph_seed_limit = resolve_graph_seed_limit(
            env_name=_PipelineOrchestrationExecutionHelpers._ENV_GRAPH_MAX_SEEDS_PER_RUN,
            default=(
                _PipelineOrchestrationExecutionHelpers._DEFAULT_GRAPH_MAX_SEEDS_PER_RUN
            ),
        )
        if len(active_graph_seed_entity_ids) > graph_seed_limit:
            active_graph_seed_entity_ids = active_graph_seed_entity_ids[
                :graph_seed_limit
            ]
        graph_requested = len(active_graph_seed_entity_ids)

        can_run_graph = extraction_status == "completed" or (
            normalized_resume_stage == "graph"
        )
        if (
            should_run_graph
            and can_run_graph
            and graph_requested > 0
            and self._graph is not None
        ):
            normalized_source = (
                normalized_source_type if normalized_source_type else "clinvar"
            )
            graph_status = "completed"
            for seed_entity_id in active_graph_seed_entity_ids:
                fallback_relations = extraction_graph_fallback_relations.get(
                    seed_entity_id,
                    (),
                )
                try:
                    try:
                        graph_outcome = await self._graph.discover_connections_for_seed(
                            research_space_id=str(research_space_id),
                            seed_entity_id=seed_entity_id,
                            source_type=normalized_source,
                            model_id=model_id,
                            relation_types=graph_relation_types,
                            max_depth=graph_max_depth,
                            shadow_mode=shadow_mode,
                            pipeline_run_id=normalized_run_id,
                            fallback_relations=fallback_relations,
                        )
                    except TypeError as exc:
                        if "fallback_relations" not in str(exc):
                            raise
                        graph_outcome = await self._graph.discover_connections_for_seed(
                            research_space_id=str(research_space_id),
                            seed_entity_id=seed_entity_id,
                            source_type=normalized_source,
                            model_id=model_id,
                            relation_types=graph_relation_types,
                            max_depth=graph_max_depth,
                            shadow_mode=shadow_mode,
                            pipeline_run_id=normalized_run_id,
                        )
                    graph_processed += 1
                    graph_persisted_relations += graph_outcome.persisted_relations_count
                    errors.extend(graph_outcome.errors)
                except Exception as exc:  # noqa: BLE001 - surfaced in run summary
                    graph_status = "failed"
                    errors.append(f"graph:{seed_entity_id}:{exc!s}")
        elif should_run_graph and can_run_graph and graph_requested > 0:
            graph_status = "failed"
            errors.append("graph:service_unavailable")
        if should_run_graph and can_run_graph and graph_requested > 0:
            pipeline_run_job = self._persist_pipeline_stage_checkpoint(
                run_job=pipeline_run_job,
                source_id=source_id,
                research_space_id=research_space_id,
                run_id=normalized_run_id,
                resume_from_stage=normalized_resume_stage,
                stage="graph",
                stage_status=graph_status,
                overall_status="running",
                stage_error=errors[-1] if graph_status == "failed" and errors else None,
            )

        completed_at = datetime.now(UTC)
        run_status: Literal["completed", "failed"] = (
            "failed"
            if any(
                stage == "failed"
                for stage in (
                    ingestion_status,
                    enrichment_status,
                    extraction_status,
                    graph_status,
                )
            )
            else "completed"
        )
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
            graph_persisted_relations=graph_persisted_relations,
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
            graph_persisted_relations=graph_persisted_relations,
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
