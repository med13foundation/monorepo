"""
Factory mixin for biomedical application services.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.domain.services import (
    EvidenceDomainService,
    GeneDomainService,
    VariantDomainService,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from src.application.services import (
        EvidenceApplicationService,
        GeneApplicationService,
        MechanismApplicationService,
        PhenotypeApplicationService,
        PublicationApplicationService,
        StatementApplicationService,
        VariantApplicationService,
    )


class BiomedicalServiceFactoryMixin:
    """Provides factory methods for biomedical application services."""

    def create_gene_application_service(
        self,
        session: Session,
    ) -> GeneApplicationService:
        from src.application.services import GeneApplicationService
        from src.infrastructure.repositories import (
            SqlAlchemyGeneRepository,
            SqlAlchemyVariantRepository,
        )

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
        from src.application.services import VariantApplicationService
        from src.infrastructure.repositories import (
            SqlAlchemyEvidenceRepository,
            SqlAlchemyVariantRepository,
        )

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
        from src.application.services import PhenotypeApplicationService
        from src.infrastructure.repositories import SqlAlchemyPhenotypeRepository

        phenotype_repository = SqlAlchemyPhenotypeRepository(session)
        return PhenotypeApplicationService(
            phenotype_repository=phenotype_repository,
        )

    def create_mechanism_application_service(
        self,
        session: Session,
    ) -> MechanismApplicationService:
        from src.application.services import MechanismApplicationService
        from src.infrastructure.repositories import SqlAlchemyMechanismRepository

        mechanism_repository = SqlAlchemyMechanismRepository(session)
        return MechanismApplicationService(
            mechanism_repository=mechanism_repository,
        )

    def create_statement_application_service(
        self,
        session: Session,
    ) -> StatementApplicationService:
        from src.application.services import StatementApplicationService
        from src.infrastructure.repositories import (
            SqlAlchemyMechanismRepository,
            SqlAlchemyStatementRepository,
        )

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
        from src.application.services import EvidenceApplicationService
        from src.infrastructure.repositories import SqlAlchemyEvidenceRepository

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
        from src.application.services import PublicationApplicationService
        from src.infrastructure.repositories import (
            SqlAlchemyEvidenceRepository,
            SqlAlchemyPublicationRepository,
        )

        publication_repository = SqlAlchemyPublicationRepository(session)
        evidence_repository = SqlAlchemyEvidenceRepository(session)
        return PublicationApplicationService(
            publication_repository=publication_repository,
            evidence_repository=evidence_repository,
        )
