"""Protocols for unified pipeline orchestration execution helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal, Protocol

if TYPE_CHECKING:
    from uuid import UUID

    from src.application.agents.services.content_enrichment_service import (
        ContentEnrichmentService,
    )
    from src.application.agents.services.entity_recognition_service import (
        EntityRecognitionService,
    )
    from src.application.agents.services.graph_connection_service import (
        GraphConnectionService,
    )
    from src.application.agents.services.graph_search_service import (
        GraphSearchService,
    )
    from src.application.services._pipeline_orchestration_contracts import (
        PipelineStageName,
        PipelineStageStatus,
    )
    from src.application.services.ingestion_scheduling_service import (
        IngestionSchedulingService,
    )
    from src.domain.entities.ingestion_job import IngestionJob
    from src.domain.repositories.research_space_repository import (
        ResearchSpaceRepository,
    )


class _PipelineExecutionSelf(Protocol):
    _ingestion: IngestionSchedulingService
    _enrichment: ContentEnrichmentService
    _extraction: EntityRecognitionService
    _graph: GraphConnectionService | None
    _graph_search: GraphSearchService | None
    _research_spaces: ResearchSpaceRepository | None

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

    def _resolve_run_id(self, raw_run_id: str | None) -> str: ...

    def _resolve_resume_stage(
        self,
        resume_from_stage: PipelineStageName | None,
    ) -> PipelineStageName | None: ...

    def _should_run_stage(
        self,
        *,
        stage: PipelineStageName,
        resume_from_stage: PipelineStageName | None,
    ) -> bool: ...

    def _normalize_graph_seed_entity_ids(
        self,
        seed_entity_ids: list[str] | None,
    ) -> list[str]: ...

    def _extract_seed_entity_ids_from_extraction_summary(
        self,
        extraction_summary: object,
    ) -> list[str]: ...

    async def _infer_seed_entity_ids_with_context(
        self,
        *,
        source_id: UUID,
        research_space_id: UUID,
        source_type: str | None,
        model_id: str | None,
    ) -> list[str]: ...

    def _build_seed_inference_prompt(
        self,
        *,
        source_id: UUID,
        research_space_id: UUID,
        source_type: str | None,
    ) -> str: ...

    def _extract_seed_entity_ids_from_graph_search(
        self,
        search_contract: object,
    ) -> list[str]: ...

    def _resolve_research_space_summary(
        self,
        *,
        research_space_id: UUID,
    ) -> str: ...

    def _resolve_recent_run_query_hints(
        self,
        *,
        source_id: UUID,
    ) -> tuple[str, ...]: ...

    def _extract_job_query_hint(
        self,
        *,
        metadata: object,
    ) -> str | None: ...

    def _resolve_latest_ingestion_job_id(
        self,
        *,
        source_id: UUID,
    ) -> UUID | None: ...


__all__ = ["_PipelineExecutionSelf"]
