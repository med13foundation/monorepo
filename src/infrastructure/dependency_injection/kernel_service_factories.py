"""
Factory mixin for kernel application services.
Split from service_factories.py to reduce module complexity.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from src.application.services.kernel import (
        KernelClaimEvidenceService,
        KernelEntityService,
        KernelObservationService,
        KernelRelationClaimService,
        KernelRelationService,
        ProvenanceService,
    )
    from src.domain.ports import ConceptPort, DictionaryPort
    from src.domain.repositories.kernel.entity_repository import KernelEntityRepository


class KernelServiceFactoryMixin:
    """Provides factory methods for kernel-related application services."""

    @staticmethod
    def _build_entity_repository(session: Session) -> KernelEntityRepository:
        from src.infrastructure.repositories.kernel import (
            SqlAlchemyKernelEntityRepository,
        )
        from src.infrastructure.security.phi_encryption import (
            build_phi_encryption_service_from_env,
            is_phi_encryption_enabled,
        )

        enable_phi_encryption = is_phi_encryption_enabled()
        phi_encryption_service = (
            build_phi_encryption_service_from_env() if enable_phi_encryption else None
        )
        return SqlAlchemyKernelEntityRepository(
            session,
            phi_encryption_service=phi_encryption_service,
            enable_phi_encryption=enable_phi_encryption,
        )

    def create_kernel_entity_service(
        self,
        session: Session,
    ) -> KernelEntityService:
        from src.application.services.kernel import KernelEntityService
        from src.infrastructure.repositories.kernel import (
            SqlAlchemyDictionaryRepository,
        )

        entity_repo = self._build_entity_repository(session)
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
        from src.infrastructure.embeddings import HybridTextEmbeddingProvider
        from src.infrastructure.llm.adapters import ArtanaDictionarySearchHarnessAdapter
        from src.infrastructure.repositories.kernel import (
            SqlAlchemyDictionaryRepository,
            SqlAlchemyKernelObservationRepository,
        )

        observation_repo = SqlAlchemyKernelObservationRepository(session)
        entity_repo = self._build_entity_repository(session)
        dictionary_repo = SqlAlchemyDictionaryRepository(session)
        embedding_provider = HybridTextEmbeddingProvider()
        search_harness = ArtanaDictionarySearchHarnessAdapter(
            dictionary_repo=dictionary_repo,
            embedding_provider=embedding_provider,
        )
        dictionary_service = DictionaryManagementService(
            dictionary_repo=dictionary_repo,
            dictionary_search_harness=search_harness,
            embedding_provider=embedding_provider,
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
            SqlAlchemyKernelRelationRepository,
        )

        relation_repo = SqlAlchemyKernelRelationRepository(session)
        entity_repo = self._build_entity_repository(session)
        dictionary_repo = SqlAlchemyDictionaryRepository(session)
        return KernelRelationService(
            relation_repo=relation_repo,
            entity_repo=entity_repo,
            dictionary_repo=dictionary_repo,
        )

    def create_kernel_relation_claim_service(
        self,
        session: Session,
    ) -> KernelRelationClaimService:
        from src.application.services.kernel import KernelRelationClaimService
        from src.infrastructure.repositories.kernel import (
            SqlAlchemyKernelRelationClaimRepository,
        )

        relation_claim_repo = SqlAlchemyKernelRelationClaimRepository(session)
        return KernelRelationClaimService(relation_claim_repo=relation_claim_repo)

    def create_kernel_claim_evidence_service(
        self,
        session: Session,
    ) -> KernelClaimEvidenceService:
        from src.application.services.kernel import KernelClaimEvidenceService
        from src.infrastructure.repositories.kernel import (
            SqlAlchemyKernelClaimEvidenceRepository,
        )

        claim_evidence_repo = SqlAlchemyKernelClaimEvidenceRepository(session)
        return KernelClaimEvidenceService(claim_evidence_repo=claim_evidence_repo)

    def create_dictionary_management_service(
        self,
        session: Session,
    ) -> DictionaryPort:
        from src.application.services.kernel import DictionaryManagementService
        from src.infrastructure.embeddings import HybridTextEmbeddingProvider
        from src.infrastructure.llm.adapters import ArtanaDictionarySearchHarnessAdapter
        from src.infrastructure.repositories.kernel import (
            SqlAlchemyDictionaryRepository,
        )

        dictionary_repo = SqlAlchemyDictionaryRepository(session)
        embedding_provider = HybridTextEmbeddingProvider()
        search_harness = ArtanaDictionarySearchHarnessAdapter(
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
        from src.application.services.kernel import ConceptManagementService
        from src.infrastructure.llm.adapters import (
            DeterministicConceptDecisionHarnessAdapter,
        )
        from src.infrastructure.repositories.kernel import SqlAlchemyConceptRepository

        concept_repo = SqlAlchemyConceptRepository(session)
        concept_harness = DeterministicConceptDecisionHarnessAdapter()
        return ConceptManagementService(
            concept_repo=concept_repo,
            concept_harness=concept_harness,
        )

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
