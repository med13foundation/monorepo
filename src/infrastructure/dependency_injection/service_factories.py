"""
Factory mixin for building application services used by the dependency container.
"""

from __future__ import annotations

import logging
import os
from contextlib import suppress
from typing import TYPE_CHECKING

from src.application.agents.services import (
    ContentEnrichmentService,
    ContentEnrichmentServiceDependencies,
    EntityRecognitionService,
    EntityRecognitionServiceDependencies,
    ExtractionService,
    ExtractionServiceDependencies,
    GovernanceService,
    GraphConnectionService,
    GraphConnectionServiceDependencies,
    GraphSearchService,
    GraphSearchServiceDependencies,
)
from src.domain.agents.models import ModelCapability
from src.infrastructure.dependency_injection import (
    analysis_service_factories,
    curation_service_factories,
    discovery_service_factories,
    kernel_service_factories,
)
from src.infrastructure.factories.ingestion_pipeline_factory import (
    create_ingestion_pipeline,
)
from src.infrastructure.llm.adapters import (
    FlujoContentEnrichmentAdapter,
    FlujoEntityRecognitionAdapter,
    FlujoExtractionAdapter,
    FlujoExtractionPolicyAdapter,
    FlujoGraphConnectionAdapter,
    FlujoGraphSearchAdapter,
    FlujoQueryAgentAdapter,
)
from src.infrastructure.llm.config.model_registry import get_model_registry
from src.infrastructure.repositories import (
    SqlAlchemyResearchSpaceRepository,
    SqlAlchemySourceDocumentRepository,
)
from src.infrastructure.repositories.kernel import (
    SqlAlchemyGraphQueryRepository,
    SqlAlchemyKernelEntityRepository,
    SqlAlchemyKernelRelationRepository,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from sqlalchemy.orm import Session

    from src.application.services import SystemStatusService
    from src.domain.agents.ports import (
        EntityRecognitionPort,
        ExtractionAgentPort,
        GraphConnectionPort,
        QueryAgentPort,
    )
    from src.domain.services import storage_metrics, storage_providers


class ApplicationServiceFactoryMixin(
    analysis_service_factories.AnalysisServiceFactoryMixin,
    curation_service_factories.CurationServiceFactoryMixin,
    discovery_service_factories.DiscoveryServiceFactoryMixin,
    kernel_service_factories.KernelServiceFactoryMixin,
):
    """Provides helper factory methods shared by the dependency container."""

    if TYPE_CHECKING:
        _storage_plugin_registry: storage_providers.StoragePluginRegistry
        _storage_metrics_recorder: storage_metrics.StorageMetricsRecorder
        _entity_recognition_agent: EntityRecognitionPort | None
        _extraction_agent: ExtractionAgentPort | None
        _graph_connection_agent: GraphConnectionPort | None
        _query_agent: QueryAgentPort | None

    if TYPE_CHECKING:

        def get_system_status_service(self) -> SystemStatusService: ...

    _logger = logging.getLogger(__name__)

    def get_query_agent(self) -> QueryAgentPort:
        if self._query_agent is None:
            registry = get_model_registry()
            model_spec = registry.get_default_model(ModelCapability.QUERY_GENERATION)
            self._query_agent = FlujoQueryAgentAdapter(model=model_spec.model_id)
        return self._query_agent

    @staticmethod
    def _build_review_queue_submitter(
        session: Session,
    ) -> Callable[[str, str, str | None, str], None]:
        from src.application.curation.repositories.review_repository import (
            SqlAlchemyReviewRepository,
        )
        from src.application.curation.services.review_service import ReviewService

        repository = SqlAlchemyReviewRepository()
        review_service = ReviewService(repository)

        def submit_review_item(
            entity_type: str,
            entity_id: str,
            research_space_id: str | None,
            priority: str,
        ) -> None:
            try:
                existing = repository.find_by_entity(
                    session,
                    entity_type=entity_type,
                    entity_id=entity_id,
                    research_space_id=research_space_id,
                )
                if existing is not None:
                    existing_status = str(existing.get("status", "")).strip().lower()
                    if existing_status == "pending":
                        return
                review_service.submit(
                    session,
                    entity_type=entity_type,
                    entity_id=entity_id,
                    priority=priority,
                    research_space_id=research_space_id,
                )
            except Exception as exc:  # noqa: BLE001
                with suppress(Exception):
                    session.rollback()
                ApplicationServiceFactoryMixin._logger.warning(
                    "Review queue submit skipped due to repository error: %s",
                    exc,
                )

        return submit_review_item

    @staticmethod
    def _is_stage_enabled(flag_name: str) -> bool:
        return os.getenv(flag_name, "1").strip() == "1"

    def get_entity_recognition_agent(self) -> EntityRecognitionPort:
        if self._entity_recognition_agent is None:
            registry = get_model_registry()
            model_spec = registry.get_default_model(
                ModelCapability.EVIDENCE_EXTRACTION,
            )
            self._entity_recognition_agent = FlujoEntityRecognitionAdapter(
                model=model_spec.model_id,
            )
        return self._entity_recognition_agent

    def get_extraction_agent(self) -> ExtractionAgentPort:
        if self._extraction_agent is None:
            registry = get_model_registry()
            model_spec = registry.get_default_model(
                ModelCapability.EVIDENCE_EXTRACTION,
            )
            self._extraction_agent = FlujoExtractionAdapter(
                model=model_spec.model_id,
            )
        return self._extraction_agent

    def create_entity_recognition_service(
        self,
        session: Session,
    ) -> EntityRecognitionService:
        dictionary_service = self.create_dictionary_management_service(session)
        governance_service = GovernanceService()
        ingestion_pipeline = create_ingestion_pipeline(session)
        registry = get_model_registry()
        model_spec = registry.get_default_model(
            ModelCapability.EVIDENCE_EXTRACTION,
        )
        entity_recognition_agent = FlujoEntityRecognitionAdapter(
            model=model_spec.model_id,
            dictionary_service=dictionary_service,
        )
        extraction_agent = FlujoExtractionAdapter(
            model=model_spec.model_id,
            dictionary_service=dictionary_service,
        )
        extraction_policy_agent = FlujoExtractionPolicyAdapter(
            model=model_spec.model_id,
        )
        extraction_service = ExtractionService(
            dependencies=ExtractionServiceDependencies(
                extraction_agent=extraction_agent,
                extraction_policy_agent=extraction_policy_agent,
                ingestion_pipeline=ingestion_pipeline,
                relation_repository=SqlAlchemyKernelRelationRepository(session),
                entity_repository=SqlAlchemyKernelEntityRepository(session),
                dictionary_service=dictionary_service,
                governance_service=governance_service,
                review_queue_submitter=self._build_review_queue_submitter(session),
            ),
        )

        return EntityRecognitionService(
            dependencies=EntityRecognitionServiceDependencies(
                entity_recognition_agent=entity_recognition_agent,
                source_document_repository=SqlAlchemySourceDocumentRepository(session),
                ingestion_pipeline=ingestion_pipeline,
                dictionary_service=dictionary_service,
                extraction_service=extraction_service,
                governance_service=governance_service,
                research_space_repository=SqlAlchemyResearchSpaceRepository(session),
            ),
            default_shadow_mode=False,
        )

    def create_extraction_service(self, session: Session) -> ExtractionService:
        dictionary_service = self.create_dictionary_management_service(session)
        registry = get_model_registry()
        model_spec = registry.get_default_model(
            ModelCapability.EVIDENCE_EXTRACTION,
        )
        extraction_agent = FlujoExtractionAdapter(
            model=model_spec.model_id,
            dictionary_service=dictionary_service,
        )
        extraction_policy_agent = FlujoExtractionPolicyAdapter(
            model=model_spec.model_id,
        )
        return ExtractionService(
            dependencies=ExtractionServiceDependencies(
                extraction_agent=extraction_agent,
                extraction_policy_agent=extraction_policy_agent,
                ingestion_pipeline=create_ingestion_pipeline(session),
                relation_repository=SqlAlchemyKernelRelationRepository(session),
                entity_repository=SqlAlchemyKernelEntityRepository(session),
                dictionary_service=dictionary_service,
                governance_service=GovernanceService(),
                review_queue_submitter=self._build_review_queue_submitter(session),
            ),
        )

    def create_graph_connection_service(
        self,
        session: Session,
    ) -> GraphConnectionService:
        dictionary_service = self.create_dictionary_management_service(session)
        relation_repository = SqlAlchemyKernelRelationRepository(session)
        graph_query_service = SqlAlchemyGraphQueryRepository(session)
        registry = get_model_registry()
        model_spec = registry.get_default_model(
            ModelCapability.EVIDENCE_EXTRACTION,
        )
        graph_connection_agent = FlujoGraphConnectionAdapter(
            model=model_spec.model_id,
            dictionary_service=dictionary_service,
            graph_query_service=graph_query_service,
            relation_repository=relation_repository,
        )
        return GraphConnectionService(
            dependencies=GraphConnectionServiceDependencies(
                graph_connection_agent=graph_connection_agent,
                relation_repository=relation_repository,
                governance_service=GovernanceService(),
                research_space_repository=SqlAlchemyResearchSpaceRepository(session),
                review_queue_submitter=self._build_review_queue_submitter(session),
            ),
        )

    def create_graph_search_service(self, session: Session) -> GraphSearchService:
        from src.application.services.research_query_service import ResearchQueryService

        dictionary_service = self.create_dictionary_management_service(session)
        graph_query_service = SqlAlchemyGraphQueryRepository(session)
        research_query_service = ResearchQueryService(
            dictionary_service=dictionary_service,
        )
        graph_search_agent = None
        if self._is_stage_enabled("MED13_ENABLE_GRAPH_SEARCH_AGENT"):
            registry = get_model_registry()
            model_spec = registry.get_default_model(ModelCapability.QUERY_GENERATION)
            graph_search_agent = FlujoGraphSearchAdapter(
                model=model_spec.model_id,
                graph_query_service=graph_query_service,
            )

        return GraphSearchService(
            dependencies=GraphSearchServiceDependencies(
                research_query_service=research_query_service,
                graph_query_service=graph_query_service,
                graph_search_agent=graph_search_agent,
                governance_service=GovernanceService(),
            ),
        )

    def create_content_enrichment_service(
        self,
        session: Session,
    ) -> ContentEnrichmentService:
        content_enrichment_agent = None
        if self._is_stage_enabled("MED13_ENABLE_CONTENT_ENRICHMENT_AGENT"):
            registry = get_model_registry()
            model_spec = registry.get_default_model(
                ModelCapability.EVIDENCE_EXTRACTION,
            )
            content_enrichment_agent = FlujoContentEnrichmentAdapter(
                model=model_spec.model_id,
            )
        return ContentEnrichmentService(
            dependencies=ContentEnrichmentServiceDependencies(
                source_document_repository=SqlAlchemySourceDocumentRepository(session),
                content_enrichment_agent=content_enrichment_agent,
                storage_coordinator=self.create_storage_operation_coordinator(session),
            ),
        )
