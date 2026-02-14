"""
Factory mixin for kernel application services.
Split from service_factories.py to reduce module complexity.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from src.application.services.kernel import (
        KernelEntityService,
        KernelObservationService,
        KernelRelationService,
        ProvenanceService,
    )
    from src.domain.ports import DictionaryPort


class KernelServiceFactoryMixin:
    """Provides factory methods for kernel-related application services."""

    def create_kernel_entity_service(
        self,
        session: Session,
    ) -> KernelEntityService:
        from src.application.services.kernel import KernelEntityService
        from src.infrastructure.repositories.kernel import (
            SqlAlchemyDictionaryRepository,
            SqlAlchemyKernelEntityRepository,
        )

        entity_repo = SqlAlchemyKernelEntityRepository(session)
        dictionary_repo = SqlAlchemyDictionaryRepository(session)
        return KernelEntityService(
            entity_repo=entity_repo,
            dictionary_repo=dictionary_repo,
        )

    def create_kernel_observation_service(
        self,
        session: Session,
    ) -> KernelObservationService:
        from src.application.services.kernel import (
            DictionaryManagementService,
            KernelObservationService,
        )
        from src.infrastructure.repositories.kernel import (
            SqlAlchemyDictionaryRepository,
            SqlAlchemyKernelEntityRepository,
            SqlAlchemyKernelObservationRepository,
        )

        observation_repo = SqlAlchemyKernelObservationRepository(session)
        entity_repo = SqlAlchemyKernelEntityRepository(session)
        dictionary_repo = SqlAlchemyDictionaryRepository(session)
        dictionary_service = DictionaryManagementService(
            dictionary_repo=dictionary_repo,
        )
        return KernelObservationService(
            observation_repo=observation_repo,
            entity_repo=entity_repo,
            dictionary_repo=dictionary_service,
        )

    def create_kernel_relation_service(
        self,
        session: Session,
    ) -> KernelRelationService:
        from src.application.services.kernel import KernelRelationService
        from src.infrastructure.repositories.kernel import (
            SqlAlchemyDictionaryRepository,
            SqlAlchemyKernelEntityRepository,
            SqlAlchemyKernelRelationRepository,
        )

        relation_repo = SqlAlchemyKernelRelationRepository(session)
        entity_repo = SqlAlchemyKernelEntityRepository(session)
        dictionary_repo = SqlAlchemyDictionaryRepository(session)
        return KernelRelationService(
            relation_repo=relation_repo,
            entity_repo=entity_repo,
            dictionary_repo=dictionary_repo,
        )

    def create_dictionary_management_service(
        self,
        session: Session,
    ) -> DictionaryPort:
        from src.application.services.kernel import DictionaryManagementService
        from src.infrastructure.repositories.kernel import (
            SqlAlchemyDictionaryRepository,
        )

        dictionary_repo = SqlAlchemyDictionaryRepository(session)
        return DictionaryManagementService(dictionary_repo=dictionary_repo)

    def create_provenance_service(
        self,
        session: Session,
    ) -> ProvenanceService:
        from src.application.services.kernel import ProvenanceService
        from src.infrastructure.repositories.kernel import (
            SqlAlchemyProvenanceRepository,
        )

        provenance_repo = SqlAlchemyProvenanceRepository(session)
        return ProvenanceService(provenance_repo=provenance_repo)
