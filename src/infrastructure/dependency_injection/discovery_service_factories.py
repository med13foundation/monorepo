"""
Factory mixin for discovery and storage application services.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.infrastructure.data_sources import (
    DeterministicPubMedSearchGateway,
    SimplePubMedPdfGateway,
)
from src.infrastructure.queries.source_query_client import HTTPQueryClient

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from src.application.services import (
        DataDiscoveryService,
        DiscoveryConfigurationService,
        PubMedDiscoveryService,
        SourceManagementService,
        StorageConfigurationService,
        StorageOperationCoordinator,
        SystemStatusService,
    )
    from src.domain.services import storage_metrics, storage_providers


class DiscoveryServiceFactoryMixin:
    """Provides factory methods for discovery and storage application services."""

    if TYPE_CHECKING:
        _storage_plugin_registry: storage_providers.StoragePluginRegistry
        _storage_metrics_recorder: storage_metrics.StorageMetricsRecorder

        def get_system_status_service(self) -> SystemStatusService: ...

    def create_discovery_configuration_service(
        self,
        session: Session,
    ) -> DiscoveryConfigurationService:
        from src.application.services import (
            DiscoveryConfigurationService,
            PubMedQueryBuilder,
        )
        from src.infrastructure.repositories import SQLAlchemyDiscoveryPresetRepository

        preset_repository = SQLAlchemyDiscoveryPresetRepository(session)
        return DiscoveryConfigurationService(
            preset_repository=preset_repository,
            pubmed_query_builder=PubMedQueryBuilder(),
        )

    def create_storage_configuration_service(
        self,
        session: Session,
    ) -> StorageConfigurationService:
        from src.application.services import StorageConfigurationService
        from src.infrastructure.repositories import (
            SqlAlchemyStorageConfigurationRepository,
            SqlAlchemyStorageOperationRepository,
        )

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
        from src.application.services import StorageOperationCoordinator

        storage_service = self.create_storage_configuration_service(session)
        return StorageOperationCoordinator(storage_service)

    def create_pubmed_discovery_service(
        self,
        session: Session,
    ) -> PubMedDiscoveryService:
        from src.application.services import PubMedDiscoveryService, PubMedQueryBuilder
        from src.infrastructure.repositories import (
            SQLAlchemyDiscoverySearchJobRepository,
        )

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

    def create_source_management_service(
        self,
        session: Session,
    ) -> SourceManagementService:
        from src.application.services import SourceManagementService
        from src.infrastructure.repositories import (
            SqlAlchemySourceTemplateRepository,
            SqlAlchemyUserDataSourceRepository,
        )

        user_data_source_repo = SqlAlchemyUserDataSourceRepository(session)
        template_repo = SqlAlchemySourceTemplateRepository(session)
        return SourceManagementService(
            user_data_source_repository=user_data_source_repo,
            source_template_repository=template_repo,
        )

    def create_data_discovery_service(self, session: Session) -> DataDiscoveryService:
        from src.application.services import (
            DataDiscoveryService,
            DataDiscoveryServiceDependencies,
            DataSourceActivationService,
        )
        from src.infrastructure.repositories import (
            SQLAlchemyDataDiscoverySessionRepository,
            SqlAlchemyDataSourceActivationRepository,
            SQLAlchemyQueryTestResultRepository,
            SQLAlchemySourceCatalogRepository,
            SqlAlchemySourceTemplateRepository,
        )

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
