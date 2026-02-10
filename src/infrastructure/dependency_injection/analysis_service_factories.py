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
        EvidenceApplicationService,
        GeneApplicationService,
        PhenotypeApplicationService,
        StorageConfigurationService,
        VariantApplicationService,
    )


class AnalysisServiceFactoryMixin:
    """Provides factory methods for analysis and reporting application services."""

    if TYPE_CHECKING:

        def create_gene_application_service(
            self,
            session: Session,
        ) -> GeneApplicationService: ...

        def create_variant_application_service(
            self,
            session: Session,
        ) -> VariantApplicationService: ...

        def create_phenotype_application_service(
            self,
            session: Session,
        ) -> PhenotypeApplicationService: ...

        def create_evidence_application_service(
            self,
            session: Session,
        ) -> EvidenceApplicationService: ...

        def create_storage_configuration_service(
            self,
            session: Session,
        ) -> StorageConfigurationService: ...

    def create_export_service(
        self,
        session: Session,
    ) -> BulkExportService:
        from src.application import export as export_module

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
    ) -> UnifiedSearchService:
        from src.application import search as search_module

        return search_module.UnifiedSearchService(
            gene_service=self.create_gene_application_service(session),
            variant_service=self.create_variant_application_service(session),
            phenotype_service=self.create_phenotype_application_service(session),
            evidence_service=self.create_evidence_application_service(session),
        )

    def create_dashboard_service(self, session: Session) -> DashboardService:
        from src.application.services import DashboardService
        from src.infrastructure.repositories import (
            SqlAlchemyEvidenceRepository,
            SqlAlchemyGeneRepository,
            SqlAlchemyPhenotypeRepository,
            SqlAlchemyPublicationRepository,
            SqlAlchemyVariantRepository,
        )

        return DashboardService(
            gene_repository=SqlAlchemyGeneRepository(session),  # type: ignore[arg-type]
            variant_repository=SqlAlchemyVariantRepository(session),  # type: ignore[arg-type]
            phenotype_repository=SqlAlchemyPhenotypeRepository(session),  # type: ignore[arg-type]
            evidence_repository=SqlAlchemyEvidenceRepository(session),  # type: ignore[arg-type]
            publication_repository=SqlAlchemyPublicationRepository(session),  # type: ignore[arg-type]
        )
