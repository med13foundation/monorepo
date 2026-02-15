"""
Factory mixin for building application services used by the dependency container.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.application.agents.services import (
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
from src.infrastructure.dependency_injection.analysis_service_factories import (
    AnalysisServiceFactoryMixin,
)
from src.infrastructure.dependency_injection.curation_service_factories import (
    CurationServiceFactoryMixin,
)
from src.infrastructure.dependency_injection.discovery_service_factories import (
    DiscoveryServiceFactoryMixin,
)
from src.infrastructure.dependency_injection.kernel_service_factories import (
    KernelServiceFactoryMixin,
)
from src.infrastructure.factories.ingestion_pipeline_factory import (
    create_ingestion_pipeline,
)
from src.infrastructure.llm.adapters import (
    FlujoEntityRecognitionAdapter,
    FlujoExtractionAdapter,
    FlujoGraphConnectionAdapter,
    FlujoQueryAgentAdapter,
)
from src.infrastructure.llm.config.model_registry import get_model_registry

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from src.application.services import SystemStatusService
    from src.domain.agents.ports.entity_recognition_port import EntityRecognitionPort
    from src.domain.agents.ports.extraction_agent_port import ExtractionAgentPort
    from src.domain.agents.ports.graph_connection_port import GraphConnectionPort
    from src.domain.agents.ports.query_agent_port import QueryAgentPort
    from src.domain.services import storage_metrics, storage_providers


class ApplicationServiceFactoryMixin(
    AnalysisServiceFactoryMixin,
    CurationServiceFactoryMixin,
    DiscoveryServiceFactoryMixin,
    KernelServiceFactoryMixin,
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
        return GraphSearchService(
            dependencies=GraphSearchServiceDependencies(
                research_query_service=research_query_service,
                graph_query_service=graph_query_service,
                graph_search_agent=None,
                governance_service=GovernanceService(),
            ),
        )
