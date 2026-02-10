"""
Factory mixin for analysis and reporting application services.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from src.application.export import BulkExportService
    from src.application.search import UnifiedSearchService
    from src.application.services import (
        DashboardService,
        StorageConfigurationService,
    )


class AnalysisServiceFactoryMixin:
    """Provides factory methods for analysis and reporting application services."""

    if TYPE_CHECKING:

        def create_storage_configuration_service(
            self,
            session: Session,
        ) -> StorageConfigurationService: ...

    def create_export_service(
        self,
        session: Session,
    ) -> BulkExportService:
        from src.application import export as export_module
        from src.infrastructure.repositories.kernel.kernel_entity_repository import (
            SqlAlchemyKernelEntityRepository,
        )
        from src.infrastructure.repositories.kernel.kernel_observation_repository import (
            SqlAlchemyKernelObservationRepository,
        )
        from src.infrastructure.repositories.kernel.kernel_relation_repository import (
            SqlAlchemyKernelRelationRepository,
        )

        return export_module.BulkExportService(
            entity_repo=SqlAlchemyKernelEntityRepository(session),
            observation_repo=SqlAlchemyKernelObservationRepository(session),
            relation_repo=SqlAlchemyKernelRelationRepository(session),
            storage_service=self.create_storage_configuration_service(session),
        )

    def create_search_service(
        self,
        session: Session,
    ) -> UnifiedSearchService:
        from src.application import search as search_module
        from src.infrastructure.repositories.kernel.kernel_entity_repository import (
            SqlAlchemyKernelEntityRepository,
        )
        from src.infrastructure.repositories.kernel.kernel_observation_repository import (
            SqlAlchemyKernelObservationRepository,
        )
        from src.infrastructure.repositories.kernel.kernel_relation_repository import (
            SqlAlchemyKernelRelationRepository,
        )

        return search_module.UnifiedSearchService(
            entity_repo=SqlAlchemyKernelEntityRepository(session),
            observation_repo=SqlAlchemyKernelObservationRepository(session),
            relation_repo=SqlAlchemyKernelRelationRepository(session),
        )

    def create_dashboard_service(self, session: Session) -> DashboardService:
        from src.application.services import DashboardService
        from src.infrastructure.repositories.kernel.kernel_entity_repository import (
            SqlAlchemyKernelEntityRepository,
        )

        return DashboardService(
            entity_repository=SqlAlchemyKernelEntityRepository(session),
        )
