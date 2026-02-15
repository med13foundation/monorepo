"""
Factory mixin for building application services used by the dependency container.
"""

from __future__ import annotations

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
    FlujoGraphConnectionAdapter,
    FlujoQueryAgentAdapter,
)
from src.infrastructure.llm.config.model_registry import get_model_registry

if TYPE_CHECKING:
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

    def get_query_agent(self) -> QueryAgentPort:
        if self._query_agent is None:
            registry = get_model_registry()
            model_spec = registry.get_default_model(ModelCapability.QUERY_GENERATION)
            self._query_agent = FlujoQueryAgentAdapter(model=model_spec.model_id)
        return self._query_agent

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
        from src.infrastructure.repositories import (
            SqlAlchemyResearchSpaceRepository,
            SqlAlchemySourceDocumentRepository,
        )

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
        extraction_service = ExtractionService(
            dependencies=ExtractionServiceDependencies(
                extraction_agent=extraction_agent,
                ingestion_pipeline=ingestion_pipeline,
                governance_service=governance_service,
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
        return ExtractionService(
            dependencies=ExtractionServiceDependencies(
                extraction_agent=extraction_agent,
                ingestion_pipeline=create_ingestion_pipeline(session),
                governance_service=GovernanceService(),
            ),
        )

    def create_graph_connection_service(
        self,
        session: Session,
    ) -> GraphConnectionService:
        from src.infrastructure.repositories.kernel import (
            SqlAlchemyGraphQueryRepository,
            SqlAlchemyKernelRelationRepository,
        )

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
            ),
        )

    def create_graph_search_service(self, session: Session) -> GraphSearchService:
        from src.application.services.research_query_service import ResearchQueryService
        from src.infrastructure.repositories.kernel import (
            SqlAlchemyGraphQueryRepository,
        )

        dictionary_service = self.create_dictionary_management_service(session)
        graph_query_service = SqlAlchemyGraphQueryRepository(session)
        research_query_service = ResearchQueryService(
            dictionary_service=dictionary_service,
        )
        graph_search_agent = None
        import os

        if os.getenv("MED13_ENABLE_GRAPH_SEARCH_AGENT", "0") == "1":
            from src.infrastructure.llm.adapters.graph_search_agent_adapter import (
                FlujoGraphSearchAdapter,
            )

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
        from src.infrastructure.repositories import SqlAlchemySourceDocumentRepository

        registry = get_model_registry()
        model_spec = registry.get_default_model(
            ModelCapability.EVIDENCE_EXTRACTION,
        )
        content_enrichment_agent = FlujoContentEnrichmentAdapter(
            model=model_spec.model_id,
        )
        return ContentEnrichmentService(
            dependencies=ContentEnrichmentServiceDependencies(
                content_enrichment_agent=content_enrichment_agent,
                source_document_repository=SqlAlchemySourceDocumentRepository(session),
                storage_coordinator=self.create_storage_operation_coordinator(session),
            ),
        )
