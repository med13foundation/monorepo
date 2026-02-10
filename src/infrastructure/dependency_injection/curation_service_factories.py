"""
Factory mixin for curation and extraction application services.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.infrastructure.extraction import RuleBasedPubMedExtractionProcessor

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from src.application.curation import CurationDetailService, CurationService
    from src.application.services import (
        EvidenceApplicationService,
        ExtractionQueueService,
        ExtractionRunnerService,
        PhenotypeApplicationService,
        PublicationExtractionService,
        StorageOperationCoordinator,
        VariantApplicationService,
    )
    from src.domain.services import (
        EvidenceDomainService,
        VariantDomainService,
    )


class CurationServiceFactoryMixin:
    """Provides factory methods for curation and extraction application services."""

    if TYPE_CHECKING:

        def get_variant_domain_service(self) -> VariantDomainService: ...
        def get_evidence_domain_service(self) -> EvidenceDomainService: ...

        def create_variant_application_service(
            self,
            session: Session,
        ) -> VariantApplicationService: ...
        def create_evidence_application_service(
            self,
            session: Session,
        ) -> EvidenceApplicationService: ...
        def create_phenotype_application_service(
            self,
            session: Session,
        ) -> PhenotypeApplicationService: ...
        def create_storage_operation_coordinator(
            self,
            session: Session,
        ) -> StorageOperationCoordinator: ...

    def create_curation_service(self, session: Session) -> CurationService:
        from src.application.curation import CurationService, SqlAlchemyReviewRepository

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
        from src.application.curation import (
            ConflictDetector,
            CurationDetailService,
            SqlAlchemyReviewRepository,
        )
        from src.infrastructure.repositories import SqlAlchemyPhenotypeRepository

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

    def create_publication_extraction_service(
        self,
        session: Session,
    ) -> PublicationExtractionService:
        from src.application.services import PublicationExtractionService
        from src.infrastructure.repositories import (
            SqlAlchemyPublicationExtractionRepository,
        )

        extraction_repository = SqlAlchemyPublicationExtractionRepository(session)
        return PublicationExtractionService(extraction_repository)

    def create_extraction_queue_service(
        self,
        session: Session,
    ) -> ExtractionQueueService:
        from src.application.services import ExtractionQueueService
        from src.infrastructure.repositories import SqlAlchemyExtractionQueueRepository

        queue_repository = SqlAlchemyExtractionQueueRepository(session)
        return ExtractionQueueService(queue_repository=queue_repository)

    def create_extraction_runner_service(
        self,
        session: Session,
    ) -> ExtractionRunnerService:
        from src.application.services import ExtractionRunnerService
        from src.infrastructure.repositories import (
            SqlAlchemyExtractionQueueRepository,
            SqlAlchemyPublicationExtractionRepository,
            SqlAlchemyPublicationRepository,
        )

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
