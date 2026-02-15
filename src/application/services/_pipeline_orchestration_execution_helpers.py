"""Execution helpers for unified pipeline orchestration."""

# mypy: disable-error-code="misc"

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Literal, Protocol
from uuid import UUID, uuid4

from src.application.services._pipeline_orchestration_contracts import (
    PIPELINE_STAGE_ORDER,
    PipelineRunSummary,
    PipelineStageName,
    PipelineStageStatus,
)

if TYPE_CHECKING:
    from src.application.agents.services.content_enrichment_service import (
        ContentEnrichmentService,
    )
    from src.application.agents.services.entity_recognition_service import (
        EntityRecognitionService,
    )
    from src.application.agents.services.graph_connection_service import (
        GraphConnectionService,
    )
    from src.application.services.ingestion_scheduling_service import (
        IngestionSchedulingService,
    )
    from src.domain.entities.ingestion_job import IngestionJob


class _PipelineExecutionSelf(Protocol):
    _ingestion: IngestionSchedulingService
    _enrichment: ContentEnrichmentService
    _extraction: EntityRecognitionService
    _graph: GraphConnectionService | None

    def _start_or_resume_pipeline_run(
        self,
        *,
        source_id: UUID,
        research_space_id: UUID,
        run_id: str,
        resume_from_stage: PipelineStageName | None,
    ) -> IngestionJob | None: ...

    def _persist_pipeline_stage_checkpoint(  # noqa: PLR0913
        self,
        *,
        run_job: IngestionJob | None,
        source_id: UUID,
        research_space_id: UUID,
        run_id: str,
        resume_from_stage: PipelineStageName | None,
        stage: PipelineStageName,
        stage_status: PipelineStageStatus,
        overall_status: Literal["running", "completed", "failed"],
        stage_error: str | None = None,
    ) -> IngestionJob | None: ...

    def _finalize_pipeline_run_checkpoint(  # noqa: PLR0913
        self,
        *,
        run_job: IngestionJob | None,
        source_id: UUID,
        research_space_id: UUID,
        run_id: str,
        resume_from_stage: PipelineStageName | None,
        run_status: Literal["completed", "failed"],
        errors: tuple[str, ...],
        created_publications: int,
        updated_publications: int,
        extraction_extracted: int,
        graph_persisted_relations: int,
    ) -> IngestionJob | None: ...


class _PipelineOrchestrationExecutionHelpers:
    """Execution-stage helpers for unified pipeline runs."""

    async def run_for_source(  # noqa: C901, PLR0913, PLR0915
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
        normalized_run_id = _PipelineOrchestrationExecutionHelpers._resolve_run_id(
            run_id,
        )
        normalized_resume_stage = (
            _PipelineOrchestrationExecutionHelpers._resolve_resume_stage(
                resume_from_stage,
            )
        )
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

        graph_requested = len(graph_seed_entity_ids or [])
        graph_processed = 0
        graph_persisted_relations = 0
        pipeline_run_job = self._start_or_resume_pipeline_run(
            source_id=source_id,
            research_space_id=research_space_id,
            run_id=normalized_run_id,
            resume_from_stage=normalized_resume_stage,
        )

        should_run_ingestion = _PipelineOrchestrationExecutionHelpers._should_run_stage(
            stage="ingestion",
            resume_from_stage=normalized_resume_stage,
        )
        should_run_enrichment = (
            _PipelineOrchestrationExecutionHelpers._should_run_stage(
                stage="enrichment",
                resume_from_stage=normalized_resume_stage,
            )
        )
        should_run_extraction = (
            _PipelineOrchestrationExecutionHelpers._should_run_stage(
                stage="extraction",
                resume_from_stage=normalized_resume_stage,
            )
        )
        should_run_graph = _PipelineOrchestrationExecutionHelpers._should_run_stage(
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
                enrichment_summary = await self._enrichment.process_pending_documents(
                    limit=max(enrichment_limit, 1),
                    source_id=source_id,
                    research_space_id=research_space_id,
                    source_type=normalized_source_type,
                    model_id=model_id,
                    pipeline_run_id=normalized_run_id,
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
                extraction_summary = await self._extraction.process_pending_documents(
                    limit=max(extraction_limit, 1),
                    source_id=source_id,
                    research_space_id=research_space_id,
                    source_type=normalized_source_type,
                    model_id=model_id,
                    shadow_mode=shadow_mode,
                    pipeline_run_id=normalized_run_id,
                )
                extraction_status = "completed"
                extraction_processed = extraction_summary.processed
                extraction_extracted = extraction_summary.extracted
                extraction_failed = extraction_summary.failed
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
            for seed_entity_id in graph_seed_entity_ids or []:
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
                "enrichment_ai_runs": enrichment_ai_runs,
                "enrichment_deterministic_runs": enrichment_deterministic_runs,
                "ingestion_status": ingestion_status,
                "enrichment_status": enrichment_status,
                "extraction_status": extraction_status,
                "graph_status": graph_status,
            },
        )

    @staticmethod
    def _resolve_run_id(raw_run_id: str | None) -> str:
        if raw_run_id is None:
            return str(uuid4())
        normalized = raw_run_id.strip()
        if normalized:
            return normalized
        return str(uuid4())

    @staticmethod
    def _resolve_resume_stage(
        resume_from_stage: PipelineStageName | None,
    ) -> PipelineStageName | None:
        if resume_from_stage is None:
            return None
        if resume_from_stage in PIPELINE_STAGE_ORDER:
            return resume_from_stage
        return None

    @staticmethod
    def _should_run_stage(
        *,
        stage: PipelineStageName,
        resume_from_stage: PipelineStageName | None,
    ) -> bool:
        if resume_from_stage is None:
            return True
        stage_index = PIPELINE_STAGE_ORDER.index(stage)
        resume_index = PIPELINE_STAGE_ORDER.index(resume_from_stage)
        return stage_index >= resume_index
