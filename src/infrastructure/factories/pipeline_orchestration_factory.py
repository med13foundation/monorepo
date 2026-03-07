"""Factory helpers for durable pipeline orchestration workers."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from src.application.services.pipeline_orchestration_service import (
    PipelineOrchestrationDependencies,
    PipelineOrchestrationService,
)
from src.database.session import SessionLocal, set_session_rls_context
from src.infrastructure.dependency_injection.dependencies import (
    get_legacy_dependency_container,
)
from src.infrastructure.factories.ingestion_scheduler_factory import (
    build_ingestion_scheduling_service,
)
from src.infrastructure.repositories import SqlAlchemyResearchSpaceRepository

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from uuid import UUID

    from src.application.agents.services._content_enrichment_types import (
        ContentEnrichmentRunSummary,
    )
    from src.application.agents.services.entity_recognition_service import (
        EntityRecognitionRunSummary,
    )
    from src.application.agents.services.graph_connection_service import (
        GraphConnectionOutcome,
    )
    from src.domain.agents.contracts.graph_connection import ProposedRelation


@asynccontextmanager
async def pipeline_orchestration_service_context() -> (  # noqa: PLR0915
    AsyncIterator[PipelineOrchestrationService]
):
    """Provide a bypass-RLS pipeline orchestration service for background workers."""
    session = SessionLocal()
    set_session_rls_context(session, bypass_rls=True)
    container = get_legacy_dependency_container()
    content_enrichment_service = None
    entity_recognition_service = None
    graph_connection_service = None
    graph_search_service = None
    try:
        scheduling_service = build_ingestion_scheduling_service(session=session)
        content_enrichment_service = container.create_content_enrichment_service(
            session,
        )
        entity_recognition_service = container.create_entity_recognition_service(
            session,
        )
        graph_connection_service = container.create_graph_connection_service(session)
        graph_search_service = container.create_graph_search_service(session)

        async def run_enrichment_stage_isolated_uow(  # noqa: PLR0913
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
            set_session_rls_context(isolated_session, bypass_rls=True)
            isolated_service = container.create_content_enrichment_service(
                isolated_session,
            )
            try:
                return await isolated_service.process_pending_documents(
                    limit=limit,
                    source_id=source_id,
                    ingestion_job_id=ingestion_job_id,
                    research_space_id=research_space_id,
                    source_type=source_type,
                    model_id=model_id,
                    pipeline_run_id=pipeline_run_id,
                )
            finally:
                await isolated_service.close()
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
            set_session_rls_context(isolated_session, bypass_rls=True)
            isolated_service = container.create_entity_recognition_service(
                isolated_session,
            )
            try:
                return await isolated_service.process_pending_documents(
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
                await isolated_service.close()
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
            set_session_rls_context(isolated_session, bypass_rls=True)
            isolated_service = container.create_graph_connection_service(
                isolated_session,
            )
            try:
                return await isolated_service.discover_connections_for_seed(
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
                await isolated_service.close()
                isolated_session.close()

        yield PipelineOrchestrationService(
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
    finally:
        if graph_search_service is not None:
            await graph_search_service.close()
        if graph_connection_service is not None:
            await graph_connection_service.close()
        if entity_recognition_service is not None:
            await entity_recognition_service.close()
        if content_enrichment_service is not None:
            await content_enrichment_service.close()
        session.close()
