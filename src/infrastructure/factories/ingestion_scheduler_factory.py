"""Factory helpers for ingestion scheduling service wiring."""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import contextmanager
from typing import TYPE_CHECKING
from uuid import UUID

from src.application.services import (
    ClinVarIngestionService,
    ExtractionQueueService,
    ExtractionRunnerService,
    IngestionSchedulingOptions,
    IngestionSchedulingService,
    PubMedDiscoveryService,
    PubMedIngestionDependencies,
    PubMedIngestionService,
    PubMedQueryBuilder,
    StorageConfigurationService,
    StorageOperationCoordinator,
)
from src.database.session import SessionLocal, set_session_rls_context
from src.database.url_resolver import resolve_sync_database_url
from src.domain.entities.user_data_source import SourceType, UserDataSource
from src.infrastructure.data_sources import (
    ClinVarSourceGateway,
    DeterministicPubMedSearchGateway,
    PubMedSourceGateway,
    SimplePubMedPdfGateway,
)
from src.infrastructure.extraction import (
    AiRequiredPubMedExtractionProcessor,
    ClinVarExtractionProcessor,
)
from src.infrastructure.factories.ingestion_pipeline_factory import (
    create_ingestion_pipeline,
)
from src.infrastructure.graph_service.pipeline import (
    build_graph_connection_seed_runner_for_service,
)
from src.infrastructure.llm.adapters.pubmed_relevance_agent_adapter import (
    ArtanaPubMedRelevanceAdapter,
)
from src.infrastructure.llm.adapters.query_agent_adapter import ArtanaQueryAgentAdapter
from src.infrastructure.repositories import (
    SQLAlchemyDiscoverySearchJobRepository,
    SqlAlchemyExtractionQueueRepository,
    SqlAlchemyIngestionJobRepository,
    SqlAlchemyIngestionSourceLockRepository,
    SqlAlchemyPublicationExtractionRepository,
    SqlAlchemyPublicationRepository,
    SqlAlchemyResearchSpaceRepository,
    SqlAlchemySourceDocumentRepository,
    SqlAlchemySourceRecordLedgerRepository,
    SqlAlchemySourceSyncStateRepository,
    SqlAlchemyStorageConfigurationRepository,
    SqlAlchemyStorageOperationRepository,
    SqlAlchemyUserDataSourceRepository,
)
from src.infrastructure.scheduling import InMemoryScheduler, PostgresScheduler
from src.infrastructure.storage import initialize_storage_plugins

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Iterator

    from sqlalchemy.orm import Session

    from src.application.services.ports.scheduler_port import SchedulerPort
    from src.domain.services.ingestion import IngestionRunContext, IngestionRunSummary

_INMEMORY_SCHEDULER = InMemoryScheduler()
_POSTGRES_PREFIXES = (
    "postgresql://",
    "postgresql+psycopg2://",
    "postgresql+psycopg://",
    "postgresql+asyncpg://",
)
_BACKEND_INMEMORY = "inmemory"
_BACKEND_POSTGRES = "postgres"
_ENV_SCHEDULER_HEARTBEAT_SECONDS = "MED13_INGESTION_SCHEDULER_HEARTBEAT_SECONDS"
_ENV_SCHEDULER_LEASE_TTL_SECONDS = "MED13_INGESTION_SCHEDULER_LEASE_TTL_SECONDS"
_ENV_SCHEDULER_STALE_RUNNING_TIMEOUT_SECONDS = (
    "MED13_INGESTION_SCHEDULER_STALE_RUNNING_TIMEOUT_SECONDS"
)
_ENV_INGESTION_JOB_HARD_TIMEOUT_SECONDS = "MED13_INGESTION_JOB_HARD_TIMEOUT_SECONDS"
_ENV_ENABLE_POST_INGESTION_PIPELINE_HOOK = "MED13_ENABLE_POST_INGESTION_PIPELINE_HOOK"
_ENV_ENABLE_POST_INGESTION_GRAPH_STAGE = "MED13_ENABLE_POST_INGESTION_GRAPH_STAGE"
_ENV_POST_INGESTION_HOOK_TIMEOUT_SECONDS = "MED13_POST_INGESTION_HOOK_TIMEOUT_SECONDS"
_ENV_POST_INGESTION_GRAPH_SEED_TIMEOUT_SECONDS = (
    "MED13_POST_INGESTION_GRAPH_SEED_TIMEOUT_SECONDS"
)
_DEFAULT_SCHEDULER_HEARTBEAT_SECONDS = 30
_DEFAULT_SCHEDULER_LEASE_TTL_SECONDS = 120
_DEFAULT_SCHEDULER_STALE_RUNNING_TIMEOUT_SECONDS = 300
_DEFAULT_INGESTION_JOB_HARD_TIMEOUT_SECONDS = 7200
_DEFAULT_POST_INGESTION_HOOK_TIMEOUT_SECONDS = 1800
_DEFAULT_POST_INGESTION_GRAPH_SEED_TIMEOUT_SECONDS = 180
_MAX_POST_INGESTION_GRAPH_SEEDS = 200

logger = logging.getLogger(__name__)


def _get_configured_scheduler_backend_name() -> str:
    configured = os.getenv(
        "MED13_INGESTION_SCHEDULER_BACKEND",
        _BACKEND_INMEMORY,
    ).strip()
    normalized = configured.lower()
    if normalized in {"in-memory", "memory"}:
        return _BACKEND_INMEMORY
    if normalized in {_BACKEND_INMEMORY, _BACKEND_POSTGRES}:
        return normalized
    msg = (
        "Unsupported MED13_INGESTION_SCHEDULER_BACKEND value. "
        "Use 'inmemory' or 'postgres'."
    )
    raise ValueError(msg)


def _resolve_scheduler_backend() -> SchedulerPort:
    backend_name = _get_configured_scheduler_backend_name()
    if backend_name == _BACKEND_INMEMORY:
        return _INMEMORY_SCHEDULER

    database_url = resolve_sync_database_url()
    if not database_url.startswith(_POSTGRES_PREFIXES):
        msg = (
            "Postgres scheduler backend requires a Postgres DATABASE_URL. "
            f"Resolved URL: {database_url}"
        )
        raise ValueError(msg)
    return PostgresScheduler(session_factory=SessionLocal)


def _read_positive_int_env(env_key: str, *, default: int) -> int:
    raw_value = os.getenv(env_key)
    if raw_value is None or not raw_value.strip():
        return default
    try:
        parsed_value = int(raw_value.strip())
    except ValueError as exc:
        msg = f"{env_key} must be a positive integer (received: {raw_value!r})"
        raise ValueError(msg) from exc
    if parsed_value <= 0:
        msg = f"{env_key} must be a positive integer (received: {raw_value!r})"
        raise ValueError(msg)
    return parsed_value


def _read_bool_env(env_key: str, *, default: bool) -> bool:
    raw_value = os.getenv(env_key)
    if raw_value is None:
        return default
    normalized = raw_value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


def _normalize_graph_seed_entity_ids(seed_entity_ids: tuple[str, ...]) -> list[str]:
    normalized_ids: list[str] = []
    for seed_entity_id in seed_entity_ids:
        normalized = seed_entity_id.strip()
        if not normalized or normalized in normalized_ids:
            continue
        normalized_ids.append(normalized)
        if len(normalized_ids) >= _MAX_POST_INGESTION_GRAPH_SEEDS:
            break
    return normalized_ids


def build_ingestion_scheduling_service(  # noqa: C901, PLR0915
    *,
    session: Session,
    scheduler: SchedulerPort | None = None,
) -> IngestionSchedulingService:
    """Create a fully wired ingestion scheduling service for the current session."""
    resolved_scheduler = scheduler or _resolve_scheduler_backend()

    publication_repository = SqlAlchemyPublicationRepository(session)
    user_source_repository = SqlAlchemyUserDataSourceRepository(session)
    job_repository = SqlAlchemyIngestionJobRepository(session)
    research_space_repository = SqlAlchemyResearchSpaceRepository(session)

    storage_configuration_repository = SqlAlchemyStorageConfigurationRepository(
        session,
    )
    storage_operation_repository = SqlAlchemyStorageOperationRepository(session)
    source_sync_state_repository = SqlAlchemySourceSyncStateRepository(session)
    source_record_ledger_repository = SqlAlchemySourceRecordLedgerRepository(session)
    source_lock_repository = SqlAlchemyIngestionSourceLockRepository(session)
    source_document_repository = SqlAlchemySourceDocumentRepository(session)
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
        publication_repository=publication_repository,
        extraction_repository=extraction_repository,
        processor_registry={
            SourceType.PUBMED.value: AiRequiredPubMedExtractionProcessor(),
            SourceType.CLINVAR.value: ClinVarExtractionProcessor(),
        },
        storage_coordinator=storage_coordinator,
    )
    post_ingestion_hook = None
    if _read_bool_env(_ENV_ENABLE_POST_INGESTION_PIPELINE_HOOK, default=True):
        from src.infrastructure.dependency_injection.dependencies import (
            # noqa: PLC0415
            get_legacy_dependency_container,
        )

        container = get_legacy_dependency_container()
        enable_post_ingestion_graph_stage = _read_bool_env(
            _ENV_ENABLE_POST_INGESTION_GRAPH_STAGE,
            default=True,
        )
        post_ingestion_graph_seed_timeout_seconds = _read_positive_int_env(
            _ENV_POST_INGESTION_GRAPH_SEED_TIMEOUT_SECONDS,
            default=_DEFAULT_POST_INGESTION_GRAPH_SEED_TIMEOUT_SECONDS,
        )
        graph_seed_runner = build_graph_connection_seed_runner_for_service()

        async def _run_enrichment_stage_isolated_uow(
            *,
            source_id: UUID,
            research_space_id: UUID,
            source_type: str,
            ingestion_job_id: UUID | None,
        ) -> None:
            isolated_session = SessionLocal()
            set_session_rls_context(isolated_session, bypass_rls=True)
            isolated_enrichment_service = container.create_content_enrichment_service(
                isolated_session,
            )
            try:
                await isolated_enrichment_service.process_pending_documents(
                    limit=200,
                    source_id=source_id,
                    ingestion_job_id=ingestion_job_id,
                    research_space_id=research_space_id,
                    source_type=source_type,
                    model_id=None,
                )
            finally:
                await isolated_enrichment_service.close()
                isolated_session.close()

        async def _run_extraction_stage_isolated_uow(
            *,
            source_id: UUID,
            research_space_id: UUID,
            source_type: str,
            ingestion_job_id: UUID | None,
        ) -> object:
            isolated_session = SessionLocal()
            set_session_rls_context(isolated_session, bypass_rls=True)
            isolated_extraction_service = container.create_entity_recognition_service(
                isolated_session,
            )
            try:
                return await isolated_extraction_service.process_pending_documents(
                    limit=200,
                    source_id=source_id,
                    ingestion_job_id=ingestion_job_id,
                    research_space_id=research_space_id,
                    source_type=source_type,
                    model_id=None,
                    shadow_mode=None,
                )
            finally:
                await isolated_extraction_service.close()
                isolated_session.close()

        async def _run_graph_seed_isolated_uow(
            *,
            source_id: UUID,
            research_space_id: UUID,
            source_type: str,
            seed_entity_id: str,
        ) -> None:
            await graph_seed_runner(
                source_id=str(source_id),
                research_space_id=str(research_space_id),
                seed_entity_id=seed_entity_id,
                source_type=source_type,
                model_id=None,
                relation_types=None,
                max_depth=2,
                shadow_mode=None,
                pipeline_run_id=None,
                fallback_relations=None,
            )

        async def _run_post_ingestion_pipeline(  # noqa: C901
            source: UserDataSource,
            summary: IngestionRunSummary,
        ) -> None:
            if source.research_space_id is None:
                return
            ingestion_job_id: UUID | None = None
            ingestion_job_id_raw: object = getattr(summary, "ingestion_job_id", None)
            if isinstance(ingestion_job_id_raw, UUID):
                ingestion_job_id = ingestion_job_id_raw
            elif isinstance(ingestion_job_id_raw, str):
                normalized_ingestion_job_id = ingestion_job_id_raw.strip()
                if normalized_ingestion_job_id:
                    try:
                        ingestion_job_id = UUID(normalized_ingestion_job_id)
                    except ValueError:
                        logger.warning(
                            "Post-ingestion hook summary had invalid ingestion_job_id",
                            extra={
                                "source_id": str(source.id),
                                "ingestion_job_id": normalized_ingestion_job_id,
                            },
                        )
            if ingestion_job_id is None:
                logger.warning(
                    "Post-ingestion hook running without ingestion_job_id scope",
                    extra={"source_id": str(source.id)},
                )
            source_type_value = source.source_type.value
            await _run_enrichment_stage_isolated_uow(
                source_id=source.id,
                research_space_id=source.research_space_id,
                source_type=source_type_value,
                ingestion_job_id=ingestion_job_id,
            )
            extraction_summary = await _run_extraction_stage_isolated_uow(
                source_id=source.id,
                ingestion_job_id=ingestion_job_id,
                research_space_id=source.research_space_id,
                source_type=source_type_value,
            )
            if not enable_post_ingestion_graph_stage:
                return
            extracted_seed_entity_ids = getattr(
                extraction_summary,
                "derived_graph_seed_entity_ids",
                (),
            )
            derived_seed_ids = _normalize_graph_seed_entity_ids(
                tuple(extracted_seed_entity_ids),
            )
            for seed_entity_id in derived_seed_ids:
                try:
                    await asyncio.wait_for(
                        _run_graph_seed_isolated_uow(
                            source_id=source.id,
                            research_space_id=source.research_space_id,
                            source_type=source_type_value,
                            seed_entity_id=seed_entity_id,
                        ),
                        timeout=post_ingestion_graph_seed_timeout_seconds,
                    )
                except TimeoutError:
                    logger.warning(
                        (
                            "Post-ingestion graph discovery timed out for "
                            "source_id=%s, seed=%s, timeout_seconds=%s"
                        ),
                        source.id,
                        seed_entity_id,
                        post_ingestion_graph_seed_timeout_seconds,
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        (
                            "Post-ingestion graph discovery failed for "
                            "source_id=%s, seed=%s: %s"
                        ),
                        source.id,
                        seed_entity_id,
                        exc,
                    )

        post_ingestion_hook = _run_post_ingestion_pipeline

    # Initialize Query Agent
    query_agent = ArtanaQueryAgentAdapter()
    pubmed_relevance_agent = ArtanaPubMedRelevanceAdapter()

    pipeline = create_ingestion_pipeline(session)

    pubmed_service = PubMedIngestionService(
        gateway=PubMedSourceGateway(
            relevance_agent=pubmed_relevance_agent,
        ),
        pipeline=pipeline,
        dependencies=PubMedIngestionDependencies(
            publication_repository=publication_repository,
            storage_service=storage_service,
            query_agent=query_agent,
            research_space_repository=research_space_repository,
            source_document_repository=source_document_repository,
        ),
    )
    clinvar_service = ClinVarIngestionService(
        gateway=ClinVarSourceGateway(),
        pipeline=pipeline,
        storage_service=storage_service,
        source_document_repository=source_document_repository,
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

    async def _run_pubmed_ingestion(
        source: UserDataSource,
        *,
        context: IngestionRunContext | None = None,
    ) -> IngestionRunSummary:
        return await pubmed_service.ingest(source, context=context)

    async def _run_clinvar_ingestion(
        source: UserDataSource,
        *,
        context: IngestionRunContext | None = None,
    ) -> IngestionRunSummary:
        return await clinvar_service.ingest(source, context=context)

    scheduler_heartbeat_seconds = _read_positive_int_env(
        _ENV_SCHEDULER_HEARTBEAT_SECONDS,
        default=_DEFAULT_SCHEDULER_HEARTBEAT_SECONDS,
    )
    scheduler_lease_ttl_seconds = _read_positive_int_env(
        _ENV_SCHEDULER_LEASE_TTL_SECONDS,
        default=_DEFAULT_SCHEDULER_LEASE_TTL_SECONDS,
    )
    scheduler_stale_running_timeout_seconds = _read_positive_int_env(
        _ENV_SCHEDULER_STALE_RUNNING_TIMEOUT_SECONDS,
        default=_DEFAULT_SCHEDULER_STALE_RUNNING_TIMEOUT_SECONDS,
    )
    ingestion_job_hard_timeout_seconds = _read_positive_int_env(
        _ENV_INGESTION_JOB_HARD_TIMEOUT_SECONDS,
        default=_DEFAULT_INGESTION_JOB_HARD_TIMEOUT_SECONDS,
    )
    post_ingestion_hook_timeout_seconds = _read_positive_int_env(
        _ENV_POST_INGESTION_HOOK_TIMEOUT_SECONDS,
        default=_DEFAULT_POST_INGESTION_HOOK_TIMEOUT_SECONDS,
    )

    ingestion_services: dict[
        SourceType,
        Callable[..., Awaitable[IngestionRunSummary]],
    ] = {
        SourceType.PUBMED: _run_pubmed_ingestion,
        SourceType.CLINVAR: _run_clinvar_ingestion,
    }

    return IngestionSchedulingService(
        scheduler=resolved_scheduler,
        source_repository=user_source_repository,
        job_repository=job_repository,
        ingestion_services=ingestion_services,
        options=IngestionSchedulingOptions(
            storage_operation_repository=storage_operation_repository,
            pubmed_discovery_service=pubmed_discovery_service,
            extraction_queue_service=extraction_queue_service,
            extraction_runner_service=extraction_runner_service,
            source_sync_state_repository=source_sync_state_repository,
            source_record_ledger_repository=source_record_ledger_repository,
            source_lock_repository=source_lock_repository,
            scheduler_heartbeat_seconds=scheduler_heartbeat_seconds,
            scheduler_lease_ttl_seconds=scheduler_lease_ttl_seconds,
            scheduler_stale_running_timeout_seconds=(
                scheduler_stale_running_timeout_seconds
            ),
            ingestion_job_hard_timeout_seconds=ingestion_job_hard_timeout_seconds,
            post_ingestion_hook_timeout_seconds=post_ingestion_hook_timeout_seconds,
            post_ingestion_hook=post_ingestion_hook,
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
    if session is None:
        set_session_rls_context(local_session, bypass_rls=True)
    try:
        service = build_ingestion_scheduling_service(
            session=local_session,
            scheduler=scheduler,
        )
        yield service
    finally:
        if session is None:
            local_session.close()
