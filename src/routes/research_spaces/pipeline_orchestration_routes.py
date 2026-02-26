"""Unified pipeline orchestration endpoints scoped to research spaces."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING, Literal
from uuid import UUID

from fastapi import Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from src.application.services.pipeline_orchestration_service import (
    PipelineOrchestrationDependencies,
    PipelineOrchestrationService,
)
from src.database.session import get_session
from src.domain.entities.ingestion_job import IngestionStatus
from src.routes.auth import get_current_active_user
from src.routes.research_spaces import (
    content_enrichment_routes,
    graph_connection_routes,
    kernel_graph_search_routes,
    knowledge_extraction_routes,
)
from src.routes.research_spaces.dependencies import (
    get_ingestion_scheduling_service_for_space,
    get_membership_service,
    require_researcher_role,
)

from .router import (
    HTTP_400_BAD_REQUEST,
    HTTP_404_NOT_FOUND,
    HTTP_500_INTERNAL_SERVER_ERROR,
    research_spaces_router,
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
    from src.application.agents.services.graph_search_service import (
        GraphSearchService,
    )
    from src.application.services import (
        IngestionSchedulingService,
        MembershipManagementService,
    )
    from src.domain.entities.user import User


logger = logging.getLogger(__name__)


class PipelineRunRequest(BaseModel):
    """Request payload for unified source pipeline execution."""

    model_config = ConfigDict(strict=False)

    source_id: str = Field(..., min_length=1, max_length=128)
    run_id: str | None = Field(default=None, min_length=1, max_length=128)
    resume_from_stage: (
        Literal["ingestion", "enrichment", "extraction", "graph"] | None
    ) = None
    enrichment_limit: int = Field(default=25, ge=1, le=200)
    extraction_limit: int = Field(default=25, ge=1, le=200)
    source_type: str | None = Field(default=None, min_length=1, max_length=64)
    model_id: str | None = Field(default=None, min_length=1, max_length=128)
    shadow_mode: bool | None = None
    force_recover_lock: bool = False
    graph_seed_entity_ids: list[str] | None = Field(default=None, max_length=200)
    graph_max_depth: int = Field(default=2, ge=1, le=4)
    graph_relation_types: list[str] | None = None


class PipelineRunResponse(BaseModel):
    """Serialized summary for one unified pipeline run."""

    model_config = ConfigDict(strict=True)

    run_id: str
    source_id: UUID
    research_space_id: UUID
    started_at: datetime
    completed_at: datetime
    status: str
    resume_from_stage: str | None = None
    ingestion_status: str
    enrichment_status: str
    extraction_status: str
    graph_status: str
    fetched_records: int
    parsed_publications: int
    created_publications: int
    updated_publications: int
    enrichment_processed: int
    enrichment_enriched: int
    enrichment_failed: int
    extraction_processed: int
    extraction_extracted: int
    extraction_failed: int
    graph_requested: int
    graph_processed: int
    graph_persisted_relations: int
    executed_query: str | None = None
    errors: list[str]
    metadata: dict[str, object] | None = None


class PipelineRunCancelResponse(BaseModel):
    """Serialized cancellation outcome for one pipeline run."""

    model_config = ConfigDict(strict=True)

    run_id: str
    source_id: UUID
    status: str
    cancelled: bool


def get_pipeline_orchestration_service(
    scheduling_service: IngestionSchedulingService = Depends(
        get_ingestion_scheduling_service_for_space,
    ),
    content_enrichment_service: ContentEnrichmentService = Depends(
        content_enrichment_routes.get_content_enrichment_service,
    ),
    entity_recognition_service: EntityRecognitionService = Depends(
        knowledge_extraction_routes.get_entity_recognition_service,
    ),
    graph_connection_service: GraphConnectionService = Depends(
        graph_connection_routes.get_graph_connection_service,
    ),
    graph_search_service: GraphSearchService = Depends(
        kernel_graph_search_routes.get_graph_search_service,
    ),
    session: Session = Depends(get_session),
) -> PipelineOrchestrationService:
    """Dependency provider for unified pipeline orchestration."""
    from src.infrastructure.repositories import SqlAlchemyResearchSpaceRepository

    return PipelineOrchestrationService(
        dependencies=PipelineOrchestrationDependencies(
            ingestion_scheduling_service=scheduling_service,
            content_enrichment_service=content_enrichment_service,
            entity_recognition_service=entity_recognition_service,
            graph_connection_service=graph_connection_service,
            graph_search_service=graph_search_service,
            research_space_repository=SqlAlchemyResearchSpaceRepository(session),
            pipeline_run_repository=scheduling_service.get_job_repository(),
        ),
    )


@research_spaces_router.post(
    "/{space_id}/pipeline/run",
    response_model=PipelineRunResponse,
    summary="Run ingestion, enrichment, extraction, and optional graph discovery",
)
async def run_unified_pipeline(
    space_id: UUID,
    request: PipelineRunRequest,
    current_user: User = Depends(get_current_active_user),
    membership_service: MembershipManagementService = Depends(get_membership_service),
    orchestration_service: PipelineOrchestrationService = Depends(
        get_pipeline_orchestration_service,
    ),
    session: Session = Depends(get_session),
) -> PipelineRunResponse:
    """Execute an end-to-end pipeline run for one source in one research space."""
    require_researcher_role(
        space_id,
        current_user.id,
        membership_service,
        session,
        current_user.role,
    )

    try:
        source_id = UUID(request.source_id)
    except ValueError as exc:
        logger.exception(
            "Invalid pipeline run source_id",
            extra={
                "path": f"/research-spaces/{space_id}/pipeline/run",
                "source_id": request.source_id,
                "source_id_type": type(request.source_id).__name__,
            },
        )
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail="source_id must be a valid UUID",
        ) from exc

    logger.info(
        "Pipeline run request accepted",
        extra={
            "space_id": str(space_id),
            "source_id": str(source_id),
            "run_id": request.run_id,
        },
    )

    try:
        summary = await orchestration_service.run_for_source(
            source_id=source_id,
            research_space_id=space_id,
            run_id=request.run_id,
            resume_from_stage=request.resume_from_stage,
            enrichment_limit=request.enrichment_limit,
            extraction_limit=request.extraction_limit,
            source_type=request.source_type,
            model_id=request.model_id,
            shadow_mode=request.shadow_mode,
            force_recover_lock=request.force_recover_lock,
            graph_seed_entity_ids=request.graph_seed_entity_ids,
            graph_max_depth=request.graph_max_depth,
            graph_relation_types=request.graph_relation_types,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unified pipeline run failed: {exc!s}",
        ) from exc

    return PipelineRunResponse(
        run_id=summary.run_id,
        source_id=summary.source_id,
        research_space_id=summary.research_space_id,
        started_at=summary.started_at,
        completed_at=summary.completed_at,
        status=summary.status,
        resume_from_stage=summary.resume_from_stage,
        ingestion_status=summary.ingestion_status,
        enrichment_status=summary.enrichment_status,
        extraction_status=summary.extraction_status,
        graph_status=summary.graph_status,
        fetched_records=summary.fetched_records,
        parsed_publications=summary.parsed_publications,
        created_publications=summary.created_publications,
        updated_publications=summary.updated_publications,
        enrichment_processed=summary.enrichment_processed,
        enrichment_enriched=summary.enrichment_enriched,
        enrichment_failed=summary.enrichment_failed,
        extraction_processed=summary.extraction_processed,
        extraction_extracted=summary.extraction_extracted,
        extraction_failed=summary.extraction_failed,
        graph_requested=summary.graph_requested,
        graph_processed=summary.graph_processed,
        graph_persisted_relations=summary.graph_persisted_relations,
        executed_query=summary.executed_query,
        errors=list(summary.errors),
        metadata=dict(summary.metadata) if summary.metadata is not None else None,
    )


@research_spaces_router.post(
    "/{space_id}/sources/{source_id}/pipeline-runs/{run_id}/cancel",
    response_model=PipelineRunCancelResponse,
    summary="Cancel an in-flight unified pipeline run",
)
def cancel_unified_pipeline_run(
    space_id: UUID,
    source_id: UUID,
    run_id: str,
    current_user: User = Depends(get_current_active_user),
    membership_service: MembershipManagementService = Depends(get_membership_service),
    orchestration_service: PipelineOrchestrationService = Depends(
        get_pipeline_orchestration_service,
    ),
    session: Session = Depends(get_session),
) -> PipelineRunCancelResponse:
    """Cancel a running unified pipeline run for one source."""
    require_researcher_role(
        space_id,
        current_user.id,
        membership_service,
        session,
        current_user.role,
    )

    try:
        cancelled_job = orchestration_service.cancel_run(
            source_id=source_id,
            run_id=run_id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Pipeline run cancellation failed: {exc!s}",
        ) from exc

    if cancelled_job is None:
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND,
            detail="Pipeline run not found for source",
        )

    return PipelineRunCancelResponse(
        run_id=run_id,
        source_id=source_id,
        status=cancelled_job.status.value,
        cancelled=cancelled_job.status == IngestionStatus.CANCELLED,
    )
