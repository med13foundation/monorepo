"""Core kernel service factory mixin."""

from __future__ import annotations

from typing import TYPE_CHECKING

import src.infrastructure.repositories.kernel as kernel_repositories
from src.application.services.kernel.concept_management_service import (
    ConceptManagementService,
)
from src.application.services.kernel.dictionary_management_service import (
    DictionaryManagementService,
)
from src.application.services.kernel.kernel_entity_service import KernelEntityService
from src.application.services.kernel.kernel_entity_similarity_service import (
    KernelEntitySimilarityService,
)
from src.application.services.kernel.kernel_observation_service import (
    KernelObservationService,
)
from src.application.services.kernel.kernel_relation_service import (
    KernelRelationService,
)
from src.application.services.kernel.kernel_relation_suggestion_service import (
    KernelRelationSuggestionService,
)
from src.application.services.kernel.provenance_service import ProvenanceService
from src.infrastructure.embeddings import HybridTextEmbeddingProvider
from src.infrastructure.factories.dictionary_search_harness_factory import (
    create_dictionary_search_harness,
)
from src.infrastructure.llm.adapters import DeterministicConceptDecisionHarnessAdapter
from src.infrastructure.security.phi_encryption import (
    build_phi_encryption_service_from_env,
    is_phi_encryption_enabled,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from src.domain.ports import ConceptPort, DictionaryPort
    from src.domain.repositories.kernel.entity_embedding_repository import (
        EntityEmbeddingRepository,
    )
    from src.domain.repositories.kernel.entity_repository import KernelEntityRepository


class KernelCoreServiceFactoryMixin:
    """Factory methods for core dictionary, entity, relation, and provenance services."""

    @staticmethod
    def _build_entity_repository(session: Session) -> KernelEntityRepository:
        enable_phi_encryption = is_phi_encryption_enabled()
        phi_encryption_service = (
            build_phi_encryption_service_from_env() if enable_phi_encryption else None
        )
        return kernel_repositories.SqlAlchemyKernelEntityRepository(
            session,
            phi_encryption_service=phi_encryption_service,
            enable_phi_encryption=enable_phi_encryption,
        )

    def create_kernel_entity_service(
        self,
        session: Session,
    ) -> KernelEntityService:
        return KernelEntityService(
            entity_repo=self._build_entity_repository(session),
            dictionary_repo=kernel_repositories.SqlAlchemyDictionaryRepository(session),
        )

    @staticmethod
    def _build_entity_embedding_repository(
        session: Session,
    ) -> EntityEmbeddingRepository:
        return kernel_repositories.SqlAlchemyEntityEmbeddingRepository(session)

    def create_kernel_entity_similarity_service(
        self,
        session: Session,
    ) -> KernelEntitySimilarityService:
        return KernelEntitySimilarityService(
            entity_repo=self._build_entity_repository(session),
            embedding_repo=self._build_entity_embedding_repository(session),
            embedding_provider=HybridTextEmbeddingProvider(),
        )

    def create_kernel_observation_service(
        self,
        session: Session,
    ) -> KernelObservationService:
        dictionary_repo = kernel_repositories.SqlAlchemyDictionaryRepository(session)
        embedding_provider = HybridTextEmbeddingProvider()
        search_harness = create_dictionary_search_harness(
            dictionary_repo=dictionary_repo,
            embedding_provider=embedding_provider,
        )
        return KernelObservationService(
            observation_repo=kernel_repositories.SqlAlchemyKernelObservationRepository(
                session,
            ),
            entity_repo=self._build_entity_repository(session),
            dictionary_repo=DictionaryManagementService(
                dictionary_repo=dictionary_repo,
                dictionary_search_harness=search_harness,
                embedding_provider=embedding_provider,
            ),
        )

    def create_kernel_relation_service(
        self,
        session: Session,
    ) -> KernelRelationService:
        return KernelRelationService(
            relation_repo=kernel_repositories.SqlAlchemyKernelRelationRepository(
                session,
            ),
            entity_repo=self._build_entity_repository(session),
        )

    def create_kernel_relation_suggestion_service(
        self,
        session: Session,
    ) -> KernelRelationSuggestionService:
        return KernelRelationSuggestionService(
            entity_repo=self._build_entity_repository(session),
            relation_repo=kernel_repositories.SqlAlchemyKernelRelationRepository(
                session,
            ),
            dictionary_repo=kernel_repositories.SqlAlchemyDictionaryRepository(session),
            embedding_repo=self._build_entity_embedding_repository(session),
        )

    def create_dictionary_management_service(
        self,
        session: Session,
    ) -> DictionaryPort:
        dictionary_repo = kernel_repositories.SqlAlchemyDictionaryRepository(session)
        embedding_provider = HybridTextEmbeddingProvider()
        search_harness = create_dictionary_search_harness(
            dictionary_repo=dictionary_repo,
            embedding_provider=embedding_provider,
        )
        return DictionaryManagementService(
            dictionary_repo=dictionary_repo,
            dictionary_search_harness=search_harness,
            embedding_provider=embedding_provider,
        )

    def create_concept_management_service(
        self,
        session: Session,
    ) -> ConceptPort:
        return ConceptManagementService(
            concept_repo=kernel_repositories.SqlAlchemyConceptRepository(session),
            concept_harness=DeterministicConceptDecisionHarnessAdapter(),
        )

    def create_provenance_service(
        self,
        session: Session,
    ) -> ProvenanceService:
        return ProvenanceService(
            provenance_repo=kernel_repositories.SqlAlchemyProvenanceRepository(session),
        )


__all__ = ["KernelCoreServiceFactoryMixin"]
