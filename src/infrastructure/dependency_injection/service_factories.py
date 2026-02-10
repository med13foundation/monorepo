"""
Factory mixin for building application services used by the dependency container.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.application import export as export_module
from src.application import search as search_module
from src.application.curation import (
    ConflictDetector,
    CurationDetailService,
    CurationService,
    SqlAlchemyReviewRepository,
)
from src.application.services import (
    DashboardService,
    DataDiscoveryService,
    DataDiscoveryServiceDependencies,
    DataSourceActivationService,
    DiscoveryConfigurationService,
    EvidenceApplicationService,
    ExtractionQueueService,
    ExtractionRunnerService,
    GeneApplicationService,
    MechanismApplicationService,
    PhenotypeApplicationService,
    PublicationApplicationService,
    PublicationExtractionService,
    PubMedDiscoveryService,
    PubMedQueryBuilder,
    SourceManagementService,
    StatementApplicationService,
    StorageConfigurationService,
    StorageOperationCoordinator,
    SystemStatusService,
    VariantApplicationService,
)
from src.domain.agents.models import ModelCapability
from src.domain.services import (
    EvidenceDomainService,
    GeneDomainService,
    VariantDomainService,
)
from src.infrastructure.data_sources import (
    DeterministicPubMedSearchGateway,
    SimplePubMedPdfGateway,
)
from src.infrastructure.extraction import RuleBasedPubMedExtractionProcessor
from src.infrastructure.llm.adapters.query_agent_adapter import FlujoQueryAgentAdapter
from src.infrastructure.llm.config.model_registry import get_model_registry
from src.infrastructure.queries.source_query_client import HTTPQueryClient
from src.infrastructure.repositories import (
    SQLAlchemyDataDiscoverySessionRepository,
    SqlAlchemyDataSourceActivationRepository,
    SQLAlchemyDiscoveryPresetRepository,
    SQLAlchemyDiscoverySearchJobRepository,
    SqlAlchemyEvidenceRepository,
    SqlAlchemyExtractionQueueRepository,
    SqlAlchemyGeneRepository,
    SqlAlchemyMechanismRepository,
    SqlAlchemyPhenotypeRepository,
    SqlAlchemyPublicationExtractionRepository,
    SqlAlchemyPublicationRepository,
    SQLAlchemyQueryTestResultRepository,
    SQLAlchemySourceCatalogRepository,
    SqlAlchemySourceTemplateRepository,
    SqlAlchemyStatementRepository,
    SqlAlchemyStorageConfigurationRepository,
    SqlAlchemyStorageOperationRepository,
    SqlAlchemyUserDataSourceRepository,
    SqlAlchemyVariantRepository,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from src.domain.agents.ports.query_agent_port import QueryAgentPort
    from src.domain.services import storage_metrics, storage_providers


class ApplicationServiceFactoryMixin:
    """Provides helper factory methods shared by the dependency container."""

    if TYPE_CHECKING:
        _storage_plugin_registry: storage_providers.StoragePluginRegistry
        _storage_metrics_recorder: storage_metrics.StorageMetricsRecorder
        _query_agent: QueryAgentPort | None

        def get_system_status_service(self) -> SystemStatusService: ...
        def get_variant_domain_service(self) -> VariantDomainService: ...
        def get_evidence_domain_service(self) -> EvidenceDomainService: ...

    def get_query_agent(self) -> QueryAgentPort:
        if self._query_agent is None:
            registry = get_model_registry()
            model_spec = registry.get_default_model(ModelCapability.QUERY_GENERATION)
            self._query_agent = FlujoQueryAgentAdapter(model=model_spec.model_id)
        return self._query_agent

    def create_gene_application_service(
        self,
        session: Session,
    ) -> GeneApplicationService:
        gene_repository = SqlAlchemyGeneRepository(session)
        gene_domain_service = GeneDomainService()
        variant_repository = SqlAlchemyVariantRepository(session)
        return GeneApplicationService(
            gene_repository=gene_repository,
            gene_domain_service=gene_domain_service,
            variant_repository=variant_repository,
        )

    def create_variant_application_service(
        self,
        session: Session,
    ) -> VariantApplicationService:
        variant_repository = SqlAlchemyVariantRepository(session)
        variant_domain_service = VariantDomainService()
        evidence_repository = SqlAlchemyEvidenceRepository(session)
        return VariantApplicationService(
            variant_repository=variant_repository,
            variant_domain_service=variant_domain_service,
            evidence_repository=evidence_repository,
        )

    def create_phenotype_application_service(
        self,
        session: Session,
    ) -> PhenotypeApplicationService:
        phenotype_repository = SqlAlchemyPhenotypeRepository(session)
        return PhenotypeApplicationService(
            phenotype_repository=phenotype_repository,
        )

    def create_mechanism_application_service(
        self,
        session: Session,
    ) -> MechanismApplicationService:
        mechanism_repository = SqlAlchemyMechanismRepository(session)
        return MechanismApplicationService(
            mechanism_repository=mechanism_repository,
        )

    def create_statement_application_service(
        self,
        session: Session,
    ) -> StatementApplicationService:
        statement_repository = SqlAlchemyStatementRepository(session)
        mechanism_repository = SqlAlchemyMechanismRepository(session)
        return StatementApplicationService(
            statement_repository=statement_repository,
            mechanism_repository=mechanism_repository,
        )

    def create_evidence_application_service(
        self,
        session: Session,
    ) -> EvidenceApplicationService:
        evidence_repository = SqlAlchemyEvidenceRepository(session)
        evidence_domain_service = EvidenceDomainService()
        return EvidenceApplicationService(
            evidence_repository=evidence_repository,
            evidence_domain_service=evidence_domain_service,
        )

    def create_publication_application_service(
        self,
        session: Session,
    ) -> PublicationApplicationService:
        publication_repository = SqlAlchemyPublicationRepository(session)
        evidence_repository = SqlAlchemyEvidenceRepository(session)
        return PublicationApplicationService(
            publication_repository=publication_repository,
            evidence_repository=evidence_repository,
        )

    def create_publication_extraction_service(
        self,
        session: Session,
    ) -> PublicationExtractionService:
        extraction_repository = SqlAlchemyPublicationExtractionRepository(session)
        return PublicationExtractionService(extraction_repository)

    def create_extraction_queue_service(
        self,
        session: Session,
    ) -> ExtractionQueueService:
        queue_repository = SqlAlchemyExtractionQueueRepository(session)
        return ExtractionQueueService(queue_repository=queue_repository)

    def create_extraction_runner_service(
        self,
        session: Session,
    ) -> ExtractionRunnerService:
        queue_repository = SqlAlchemyExtractionQueueRepository(session)
        publication_repository = SqlAlchemyPublicationRepository(session)
        extraction_repository = SqlAlchemyPublicationExtractionRepository(session)
        processor = RuleBasedPubMedExtractionProcessor()
        storage_coordinator = self.create_storage_operation_coordinator(session)
        return ExtractionRunnerService(
            queue_repository=queue_repository,
            publication_repository=publication_repository,
            extraction_repository=extraction_repository,
            processor=processor,
            storage_coordinator=storage_coordinator,
        )

    def create_discovery_configuration_service(
        self,
        session: Session,
    ) -> DiscoveryConfigurationService:
        preset_repository = SQLAlchemyDiscoveryPresetRepository(session)
        return DiscoveryConfigurationService(
            preset_repository=preset_repository,
            pubmed_query_builder=PubMedQueryBuilder(),
        )

    def create_storage_configuration_service(
        self,
        session: Session,
    ) -> StorageConfigurationService:
        configuration_repository = SqlAlchemyStorageConfigurationRepository(session)
        operation_repository = SqlAlchemyStorageOperationRepository(session)
        system_status_service = self.get_system_status_service()
        return StorageConfigurationService(
            configuration_repository=configuration_repository,
            operation_repository=operation_repository,
            plugin_registry=self._storage_plugin_registry,
            system_status_service=system_status_service,
            metrics_recorder=self._storage_metrics_recorder,
        )

    def create_storage_operation_coordinator(
        self,
        session: Session,
    ) -> StorageOperationCoordinator:
        """Return a coordinator for storing artifacts via storage providers."""

        storage_service = self.create_storage_configuration_service(session)
        return StorageOperationCoordinator(storage_service)

    def create_pubmed_discovery_service(
        self,
        session: Session,
    ) -> PubMedDiscoveryService:
        job_repository = SQLAlchemyDiscoverySearchJobRepository(session)
        query_builder = PubMedQueryBuilder()
        search_gateway = DeterministicPubMedSearchGateway(query_builder)
        pdf_gateway = SimplePubMedPdfGateway()
        storage_coordinator = self.create_storage_operation_coordinator(session)
        return PubMedDiscoveryService(
            job_repository=job_repository,
            query_builder=query_builder,
            search_gateway=search_gateway,
            pdf_gateway=pdf_gateway,
            storage_coordinator=storage_coordinator,
        )

    def create_curation_service(self, session: Session) -> CurationService:
        return CurationService(
            review_repository=SqlAlchemyReviewRepository(),
            variant_service=self.create_variant_application_service(session),
            evidence_service=self.create_evidence_application_service(session),
            phenotype_service=self.create_phenotype_application_service(session),
        )

    def create_curation_detail_service(
        self,
        session: Session,
    ) -> CurationDetailService:
        conflict_detector = ConflictDetector(
            variant_domain_service=self.get_variant_domain_service(),
            evidence_domain_service=self.get_evidence_domain_service(),
        )

        return CurationDetailService(
            variant_service=self.create_variant_application_service(session),
            evidence_service=self.create_evidence_application_service(session),
            phenotype_repository=SqlAlchemyPhenotypeRepository(session),
            conflict_detector=conflict_detector,
            review_repository=SqlAlchemyReviewRepository(),
            db_session=session,
        )

    def create_export_service(
        self,
        session: Session,
    ) -> export_module.BulkExportService:
        return export_module.BulkExportService(
            gene_service=self.create_gene_application_service(session),
            variant_service=self.create_variant_application_service(session),
            phenotype_service=self.create_phenotype_application_service(session),
            evidence_service=self.create_evidence_application_service(session),
            storage_service=self.create_storage_configuration_service(session),
        )

    def create_search_service(
        self,
        session: Session,
    ) -> search_module.UnifiedSearchService:
        return search_module.UnifiedSearchService(
            gene_service=self.create_gene_application_service(session),
            variant_service=self.create_variant_application_service(session),
            phenotype_service=self.create_phenotype_application_service(session),
            evidence_service=self.create_evidence_application_service(session),
        )

    def create_dashboard_service(self, session: Session) -> DashboardService:
        return DashboardService(
            gene_repository=SqlAlchemyGeneRepository(session),
            variant_repository=SqlAlchemyVariantRepository(session),
            phenotype_repository=SqlAlchemyPhenotypeRepository(session),
            evidence_repository=SqlAlchemyEvidenceRepository(session),
            publication_repository=SqlAlchemyPublicationRepository(session),
        )

    def create_source_management_service(
        self,
        session: Session,
    ) -> SourceManagementService:
        user_data_source_repo = SqlAlchemyUserDataSourceRepository(session)
        template_repo = SqlAlchemySourceTemplateRepository(session)
        return SourceManagementService(
            user_data_source_repository=user_data_source_repo,
            source_template_repository=template_repo,
        )

    def create_data_discovery_service(self, session: Session) -> DataDiscoveryService:
        session_repo = SQLAlchemyDataDiscoverySessionRepository(session)
        catalog_repo = SQLAlchemySourceCatalogRepository(session)
        query_repo = SQLAlchemyQueryTestResultRepository(session)

        query_client = HTTPQueryClient()

        source_service = self.create_source_management_service(session)
        template_repo = SqlAlchemySourceTemplateRepository(session)
        activation_repo = SqlAlchemyDataSourceActivationRepository(session)
        activation_service = DataSourceActivationService(activation_repo)

        return DataDiscoveryService(
            data_discovery_session_repository=session_repo,
            source_catalog_repository=catalog_repo,
            query_result_repository=query_repo,
            source_query_client=query_client,
            source_management_service=source_service,
            dependencies=DataDiscoveryServiceDependencies(
                source_template_repository=template_repo,
                activation_service=activation_service,
            ),
        )


__all__ = ["ApplicationServiceFactoryMixin"]
