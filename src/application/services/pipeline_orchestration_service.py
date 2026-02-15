"""Unified orchestration service for end-to-end source pipeline execution."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Literal
from uuid import UUID, uuid4

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
    from src.type_definitions.common import JSONObject


PipelineStageStatus = Literal["completed", "failed", "skipped"]
PipelineStageName = Literal["ingestion", "enrichment", "extraction", "graph"]
_PIPELINE_STAGE_ORDER: tuple[PipelineStageName, ...] = (
    "ingestion",
    "enrichment",
    "extraction",
    "graph",
)


@dataclass(frozen=True)
class PipelineOrchestrationDependencies:
    """Dependencies required for end-to-end pipeline orchestration."""

    ingestion_scheduling_service: IngestionSchedulingService
    content_enrichment_service: ContentEnrichmentService
    entity_recognition_service: EntityRecognitionService
    graph_connection_service: GraphConnectionService | None = None


@dataclass(frozen=True)
class PipelineRunSummary:
    """Summary of one orchestrated pipeline run."""

    run_id: str
    source_id: UUID
    research_space_id: UUID
    started_at: datetime
    completed_at: datetime
    status: Literal["completed", "failed"]
    resume_from_stage: PipelineStageName | None
    ingestion_status: PipelineStageStatus
    enrichment_status: PipelineStageStatus
    extraction_status: PipelineStageStatus
    graph_status: PipelineStageStatus
    fetched_records: int = 0
    parsed_publications: int = 0
    created_publications: int = 0
    updated_publications: int = 0
    enrichment_processed: int = 0
    enrichment_enriched: int = 0
    enrichment_failed: int = 0
    extraction_processed: int = 0
    extraction_extracted: int = 0
    extraction_failed: int = 0
    graph_requested: int = 0
    graph_processed: int = 0
    graph_persisted_relations: int = 0
    executed_query: str | None = None
    errors: tuple[str, ...] = ()
    metadata: JSONObject | None = None


class PipelineOrchestrationService:
    """Run ingestion -> enrichment -> extraction -> graph stages with one run id."""

    def __init__(self, dependencies: PipelineOrchestrationDependencies) -> None:
        self._ingestion = dependencies.ingestion_scheduling_service
        self._enrichment = dependencies.content_enrichment_service
        self._extraction = dependencies.entity_recognition_service
        self._graph = dependencies.graph_connection_service

    async def run_for_source(  # noqa: C901, PLR0913, PLR0915
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

        enrichment_processed = 0
        enrichment_enriched = 0
        enrichment_failed = 0

        extraction_processed = 0
        extraction_extracted = 0
        extraction_failed = 0

        graph_requested = len(graph_seed_entity_ids or [])
        graph_processed = 0
        graph_persisted_relations = 0

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
            except Exception as exc:  # noqa: BLE001 - surfaced in run summary
                ingestion_status = "failed"
                errors.append(f"ingestion:{exc!s}")

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
                errors.extend(enrichment_summary.errors)
            except Exception as exc:  # noqa: BLE001 - surfaced in run summary
                enrichment_status = "failed"
                errors.append(f"enrichment:{exc!s}")

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
        if resume_from_stage in _PIPELINE_STAGE_ORDER:
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
        stage_index = _PIPELINE_STAGE_ORDER.index(stage)
        resume_index = _PIPELINE_STAGE_ORDER.index(resume_from_stage)
        return stage_index >= resume_index


__all__ = [
    "PipelineOrchestrationDependencies",
    "PipelineOrchestrationService",
    "PipelineRunSummary",
]
