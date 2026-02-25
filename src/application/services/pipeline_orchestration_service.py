"""Unified orchestration service for end-to-end source pipeline execution."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

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
    from src.application.services.ingestion_scheduling_service import (
        IngestionSchedulingService,
    )
    from src.domain.entities.ingestion_job import IngestionJob
    from src.domain.repositories.ingestion_job_repository import IngestionJobRepository
    from src.domain.repositories.research_space_repository import (
        ResearchSpaceRepository,
    )


@dataclass(frozen=True)
class PipelineOrchestrationDependencies:
    """Dependencies required for end-to-end pipeline orchestration."""

    ingestion_scheduling_service: IngestionSchedulingService
    content_enrichment_service: ContentEnrichmentService
    entity_recognition_service: EntityRecognitionService
    graph_connection_service: GraphConnectionService | None = None
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
        self._graph = dependencies.graph_connection_service
        self._graph_search = dependencies.graph_search_service
        self._research_spaces = dependencies.research_space_repository
        self._pipeline_runs = dependencies.pipeline_run_repository

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


__all__ = [
    "PipelineOrchestrationDependencies",
    "PipelineOrchestrationService",
    "PipelineRunSummary",
    "PipelineStageName",
    "PipelineStageStatus",
]
