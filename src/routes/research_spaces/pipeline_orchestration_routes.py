"""Unified pipeline orchestration endpoints scoped to research spaces."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING, Literal
from uuid import UUID

from fastapi import Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from src.application.services.pipeline_orchestration_service import (
    ActivePipelineRunExistsError,
    PipelineOrchestrationDependencies,
    PipelineOrchestrationService,
    PipelineQueueFullError,
)
from src.database.session import get_session
from src.domain.entities.ingestion_job import IngestionStatus
from src.domain.entities.user import UserRole
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
    from src.application.services import (
        IngestionSchedulingService,
        MembershipManagementService,
    )
    from src.domain.agents.contracts.graph_connection import ProposedRelation
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


class PipelineRunAcceptedResponse(BaseModel):
    """Serialized queue-acceptance payload for one pipeline run."""

    model_config = ConfigDict(strict=True)

    run_id: str
    source_id: UUID
    research_space_id: UUID
    status: str
    accepted_at: datetime


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
    current_user: User = Depends(get_current_active_user),
    session: Session = Depends(get_session),
) -> PipelineOrchestrationService:
    """Dependency provider for unified pipeline orchestration."""
    from src.database.session import SessionLocal, set_session_rls_context
    from src.infrastructure.dependency_injection.dependencies import (
        get_legacy_dependency_container,
    )
    from src.infrastructure.repositories import SqlAlchemyResearchSpaceRepository

    container = get_legacy_dependency_container()
    is_admin_user = current_user.role == UserRole.ADMIN

    async def run_enrichment_stage_isolated_uow(
        *,
        limit: int,
        source_id: UUID | None,
        ingestion_job_id: UUID | None,
        research_space_id: UUID | None,
        source_type: str | None,
        model_id: str | None,
        pipeline_run_id: str | None,
    ) -> ContentEnrichmentRunSummary:
        isolated_session = SessionLocal()
        set_session_rls_context(
            isolated_session,
            current_user_id=current_user.id,
            has_phi_access=is_admin_user,
            is_admin=is_admin_user,
            bypass_rls=False,
        )
        isolated_enrichment_service = container.create_content_enrichment_service(
            isolated_session,
        )
        try:
            return await isolated_enrichment_service.process_pending_documents(
                limit=limit,
                source_id=source_id,
                ingestion_job_id=ingestion_job_id,
                research_space_id=research_space_id,
                source_type=source_type,
                model_id=model_id,
                pipeline_run_id=pipeline_run_id,
            )
        finally:
            await isolated_enrichment_service.close()
            isolated_session.close()

    async def run_extraction_stage_isolated_uow(  # noqa: PLR0913
        *,
        limit: int,
        source_id: UUID | None,
        ingestion_job_id: UUID | None,
        research_space_id: UUID | None,
        source_type: str | None,
        model_id: str | None,
        shadow_mode: bool | None,
        pipeline_run_id: str | None,
    ) -> EntityRecognitionRunSummary:
        isolated_session = SessionLocal()
        set_session_rls_context(
            isolated_session,
            current_user_id=current_user.id,
            has_phi_access=is_admin_user,
            is_admin=is_admin_user,
            bypass_rls=False,
        )
        isolated_extraction_service = container.create_entity_recognition_service(
            isolated_session,
        )
        try:
            return await isolated_extraction_service.process_pending_documents(
                limit=limit,
                source_id=source_id,
                ingestion_job_id=ingestion_job_id,
                research_space_id=research_space_id,
                source_type=source_type,
                model_id=model_id,
                shadow_mode=shadow_mode,
                pipeline_run_id=pipeline_run_id,
            )
        finally:
            await isolated_extraction_service.close()
            isolated_session.close()

    async def run_graph_seed_isolated_uow(  # noqa: PLR0913
        *,
        source_id: str,
        research_space_id: str,
        seed_entity_id: str,
        source_type: str,
        model_id: str | None,
        relation_types: list[str] | None,
        max_depth: int,
        shadow_mode: bool | None,
        pipeline_run_id: str | None,
        fallback_relations: tuple[ProposedRelation, ...] | None,
    ) -> GraphConnectionOutcome:
        isolated_session = SessionLocal()
        set_session_rls_context(
            isolated_session,
            current_user_id=current_user.id,
            has_phi_access=is_admin_user,
            is_admin=is_admin_user,
            bypass_rls=False,
        )
        isolated_graph_service = container.create_graph_connection_service(
            isolated_session,
        )
        try:
            return await isolated_graph_service.discover_connections_for_seed(
                research_space_id=research_space_id,
                seed_entity_id=seed_entity_id,
                source_id=source_id,
                source_type=source_type,
                model_id=model_id,
                relation_types=relation_types,
                max_depth=max_depth,
                shadow_mode=shadow_mode,
                pipeline_run_id=pipeline_run_id,
                fallback_relations=fallback_relations,
            )
        finally:
            await isolated_graph_service.close()
            isolated_session.close()

    return PipelineOrchestrationService(
        dependencies=PipelineOrchestrationDependencies(
            ingestion_scheduling_service=scheduling_service,
            content_enrichment_service=content_enrichment_service,
            entity_recognition_service=entity_recognition_service,
            content_enrichment_stage_runner=run_enrichment_stage_isolated_uow,
            entity_recognition_stage_runner=run_extraction_stage_isolated_uow,
            graph_connection_service=graph_connection_service,
            graph_connection_seed_runner=run_graph_seed_isolated_uow,
            graph_search_service=graph_search_service,
            research_space_repository=SqlAlchemyResearchSpaceRepository(session),
            pipeline_run_repository=scheduling_service.get_job_repository(),
        ),
    )


@research_spaces_router.post(
    "/{space_id}/pipeline/run",
    response_model=PipelineRunAcceptedResponse,
    status_code=202,
    summary="Queue ingestion, enrichment, extraction, and optional graph discovery",
)
def run_unified_pipeline(
    space_id: UUID,
    request: PipelineRunRequest,
    response: Response,
    current_user: User = Depends(get_current_active_user),
    membership_service: MembershipManagementService = Depends(get_membership_service),
    orchestration_service: PipelineOrchestrationService = Depends(
        get_pipeline_orchestration_service,
    ),
    session: Session = Depends(get_session),
) -> PipelineRunAcceptedResponse:
    """Queue an end-to-end pipeline run for one source in one research space."""
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
        queued_run = orchestration_service.enqueue_run(
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
    except ActivePipelineRunExistsError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "message": str(exc),
                "run_id": exc.run_id,
            },
        ) from exc
    except PipelineQueueFullError as exc:
        raise HTTPException(
            status_code=503,
            detail="Pipeline queue is full; retry later",
            headers={"Retry-After": str(exc.retry_after_seconds)},
        ) from exc
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

    response.headers["Location"] = (
        f"/research-spaces/{space_id}/sources/{source_id}/workflow-monitor"
        f"?run_id={queued_run.run_id}"
    )
    return PipelineRunAcceptedResponse(
        run_id=queued_run.run_id,
        source_id=queued_run.source_id,
        research_space_id=queued_run.research_space_id,
        status=queued_run.status,
        accepted_at=queued_run.accepted_at,
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
