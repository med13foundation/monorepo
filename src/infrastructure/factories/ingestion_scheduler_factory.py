"""Factory helpers for building ingestion scheduling services with infrastructure adapters."""

from __future__ import annotations

from contextlib import contextmanager
from typing import TYPE_CHECKING

from src.application.services import (
    ClinVarIngestionService,
    ExtractionQueueService,
    ExtractionRunnerService,
    IngestionSchedulingOptions,
    IngestionSchedulingService,
    PubMedDiscoveryService,
    PubMedIngestionService,
    PubMedQueryBuilder,
    StorageConfigurationService,
    StorageOperationCoordinator,
)
from src.database.session import SessionLocal
from src.domain.entities.user_data_source import SourceType, UserDataSource
from src.infrastructure.data_sources import (
    ClinVarSourceGateway,
    DeterministicPubMedSearchGateway,
    PubMedSourceGateway,
    SimplePubMedPdfGateway,
)
from src.infrastructure.extraction import RuleBasedPubMedExtractionProcessor
from src.infrastructure.factories.ingestion_pipeline_factory import (
    create_ingestion_pipeline,
)
from src.infrastructure.llm.adapters.query_agent_adapter import FlujoQueryAgentAdapter
from src.infrastructure.repositories import (
    SQLAlchemyDiscoverySearchJobRepository,
    SqlAlchemyExtractionQueueRepository,
    SqlAlchemyIngestionJobRepository,
    SqlAlchemyPublicationExtractionRepository,
    SqlAlchemyPublicationRepository,
    SqlAlchemyResearchSpaceRepository,
    SqlAlchemyStorageConfigurationRepository,
    SqlAlchemyStorageOperationRepository,
    SqlAlchemyUserDataSourceRepository,
)
from src.infrastructure.scheduling import InMemoryScheduler
from src.infrastructure.storage import initialize_storage_plugins

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Iterator

    from sqlalchemy.orm import Session

    from src.application.services.ports.scheduler_port import SchedulerPort
    from src.domain.services.ingestion import IngestionRunSummary

SCHEDULER_BACKEND = InMemoryScheduler()


def build_ingestion_scheduling_service(
    *,
    session: Session,
    scheduler: SchedulerPort | None = None,
) -> IngestionSchedulingService:
    """Create a fully wired ingestion scheduling service for the current session."""
    publication_repository = SqlAlchemyPublicationRepository(session)
    user_source_repository = SqlAlchemyUserDataSourceRepository(session)
    job_repository = SqlAlchemyIngestionJobRepository(session)
    research_space_repository = SqlAlchemyResearchSpaceRepository(session)

    storage_configuration_repository = SqlAlchemyStorageConfigurationRepository(
        session,
    )
    storage_operation_repository = SqlAlchemyStorageOperationRepository(session)
    storage_service = StorageConfigurationService(
        configuration_repository=storage_configuration_repository,
        operation_repository=storage_operation_repository,
        plugin_registry=initialize_storage_plugins(),
    )
    storage_coordinator = StorageOperationCoordinator(storage_service)
    extraction_queue_repository = SqlAlchemyExtractionQueueRepository(session)
    extraction_queue_service = ExtractionQueueService(
        queue_repository=extraction_queue_repository,
    )
    extraction_repository = SqlAlchemyPublicationExtractionRepository(session)
    extraction_runner_service = ExtractionRunnerService(
        queue_repository=extraction_queue_repository,
        publication_repository=publication_repository,  # type: ignore[arg-type]
        extraction_repository=extraction_repository,
        processor=RuleBasedPubMedExtractionProcessor(),
        storage_coordinator=storage_coordinator,
    )

    # Initialize Query Agent
    query_agent = FlujoQueryAgentAdapter()

    pipeline = create_ingestion_pipeline(session)

    pubmed_service = PubMedIngestionService(
        gateway=PubMedSourceGateway(),
        pipeline=pipeline,
        publication_repository=publication_repository,  # type: ignore[arg-type]
        storage_service=storage_service,
        query_agent=query_agent,
        research_space_repository=research_space_repository,
    )
    clinvar_service = ClinVarIngestionService(
        gateway=ClinVarSourceGateway(),
        pipeline=pipeline,
        storage_service=storage_service,
    )

    discovery_job_repository = SQLAlchemyDiscoverySearchJobRepository(session)
    query_builder = PubMedQueryBuilder()
    search_gateway = DeterministicPubMedSearchGateway(query_builder)
    pdf_gateway = SimplePubMedPdfGateway()
    pubmed_discovery_service = PubMedDiscoveryService(
        job_repository=discovery_job_repository,
        query_builder=query_builder,
        search_gateway=search_gateway,
        pdf_gateway=pdf_gateway,
        storage_coordinator=storage_coordinator,
    )

    async def _run_pubmed_ingestion(source: UserDataSource) -> IngestionRunSummary:
        return await pubmed_service.ingest(source)

    async def _run_clinvar_ingestion(source: UserDataSource) -> IngestionRunSummary:
        return await clinvar_service.ingest(source)

    ingestion_services: dict[
        SourceType,
        Callable[[UserDataSource], Awaitable[IngestionRunSummary]],
    ] = {
        SourceType.PUBMED: _run_pubmed_ingestion,
        SourceType.CLINVAR: _run_clinvar_ingestion,
    }

    return IngestionSchedulingService(
        scheduler=scheduler or SCHEDULER_BACKEND,
        source_repository=user_source_repository,
        job_repository=job_repository,
        ingestion_services=ingestion_services,
        options=IngestionSchedulingOptions(
            storage_operation_repository=storage_operation_repository,
            pubmed_discovery_service=pubmed_discovery_service,
            extraction_queue_service=extraction_queue_service,
            extraction_runner_service=extraction_runner_service,
        ),
    )


@contextmanager
def ingestion_scheduling_service_context(
    *,
    session: Session | None = None,
    scheduler: SchedulerPort | None = None,
) -> Iterator[IngestionSchedulingService]:
    """Context manager that yields a scheduling service and closes the session."""
    local_session = session or SessionLocal()
    try:
        service = build_ingestion_scheduling_service(
            session=local_session,
            scheduler=scheduler,
        )
        yield service
    finally:
        if session is None:
            local_session.close()
