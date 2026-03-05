"""
Factory mixin for kernel application services.
Split from service_factories.py to reduce module complexity.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.application.agents.services.hypothesis_generation_service import (
    HypothesisGenerationService,
    HypothesisGenerationServiceDependencies,
)
from src.application.services.kernel import (
    ConceptManagementService,
    DictionaryManagementService,
    KernelClaimEvidenceService,
    KernelClaimParticipantService,
    KernelClaimRelationService,
    KernelEntityService,
    KernelEntitySimilarityService,
    KernelObservationService,
    KernelRelationClaimService,
    KernelRelationService,
    KernelRelationSuggestionService,
    ProvenanceService,
)
from src.domain.agents.models import ModelCapability
from src.infrastructure.embeddings import HybridTextEmbeddingProvider
from src.infrastructure.llm.adapters import (
    ArtanaDictionarySearchHarnessAdapter,
    ArtanaGraphConnectionAdapter,
    DeterministicConceptDecisionHarnessAdapter,
)
from src.infrastructure.llm.config.model_registry import get_model_registry
from src.infrastructure.repositories.kernel import (
    SqlAlchemyConceptRepository,
    SqlAlchemyDictionaryRepository,
    SqlAlchemyEntityEmbeddingRepository,
    SqlAlchemyGraphQueryRepository,
    SqlAlchemyKernelClaimEvidenceRepository,
    SqlAlchemyKernelClaimParticipantRepository,
    SqlAlchemyKernelClaimRelationRepository,
    SqlAlchemyKernelEntityRepository,
    SqlAlchemyKernelObservationRepository,
    SqlAlchemyKernelRelationClaimRepository,
    SqlAlchemyKernelRelationRepository,
    SqlAlchemyProvenanceRepository,
)
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


class KernelServiceFactoryMixin:
    """Provides factory methods for kernel-related application services."""

    @staticmethod
    def _build_entity_repository(session: Session) -> KernelEntityRepository:
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
        entity_repo = self._build_entity_repository(session)
        dictionary_repo = SqlAlchemyDictionaryRepository(session)
        return KernelEntityService(
            entity_repo=entity_repo,
            dictionary_repo=dictionary_repo,
        )

    @staticmethod
    def _build_entity_embedding_repository(
        session: Session,
    ) -> EntityEmbeddingRepository:
        return SqlAlchemyEntityEmbeddingRepository(session)

    def create_kernel_entity_similarity_service(
        self,
        session: Session,
    ) -> KernelEntitySimilarityService:
        entity_repo = self._build_entity_repository(session)
        entity_embedding_repo = self._build_entity_embedding_repository(session)
        embedding_provider = HybridTextEmbeddingProvider()
        return KernelEntitySimilarityService(
            entity_repo=entity_repo,
            embedding_repo=entity_embedding_repo,
            embedding_provider=embedding_provider,
        )

    def create_kernel_observation_service(
        self,
        session: Session,
    ) -> KernelObservationService:
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
        relation_repo = SqlAlchemyKernelRelationRepository(session)
        entity_repo = self._build_entity_repository(session)
        dictionary_repo = SqlAlchemyDictionaryRepository(session)
        return KernelRelationService(
            relation_repo=relation_repo,
            entity_repo=entity_repo,
            dictionary_repo=dictionary_repo,
        )

    def create_kernel_relation_suggestion_service(
        self,
        session: Session,
    ) -> KernelRelationSuggestionService:
        relation_repo = SqlAlchemyKernelRelationRepository(session)
        entity_repo = self._build_entity_repository(session)
        dictionary_repo = SqlAlchemyDictionaryRepository(session)
        embedding_repo = self._build_entity_embedding_repository(session)
        return KernelRelationSuggestionService(
            entity_repo=entity_repo,
            relation_repo=relation_repo,
            dictionary_repo=dictionary_repo,
            embedding_repo=embedding_repo,
        )

    def create_kernel_relation_claim_service(
        self,
        session: Session,
    ) -> KernelRelationClaimService:
        relation_claim_repo = SqlAlchemyKernelRelationClaimRepository(session)
        return KernelRelationClaimService(relation_claim_repo=relation_claim_repo)

    def create_kernel_claim_participant_service(
        self,
        session: Session,
    ) -> KernelClaimParticipantService:
        claim_participant_repo = SqlAlchemyKernelClaimParticipantRepository(session)
        return KernelClaimParticipantService(
            claim_participant_repo=claim_participant_repo,
        )

    def create_kernel_claim_relation_service(
        self,
        session: Session,
    ) -> KernelClaimRelationService:
        claim_relation_repo = SqlAlchemyKernelClaimRelationRepository(session)
        return KernelClaimRelationService(claim_relation_repo=claim_relation_repo)

    def create_kernel_claim_evidence_service(
        self,
        session: Session,
    ) -> KernelClaimEvidenceService:
        claim_evidence_repo = SqlAlchemyKernelClaimEvidenceRepository(session)
        return KernelClaimEvidenceService(claim_evidence_repo=claim_evidence_repo)

    def create_dictionary_management_service(
        self,
        session: Session,
    ) -> DictionaryPort:
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
        provenance_repo = SqlAlchemyProvenanceRepository(session)
        return ProvenanceService(provenance_repo=provenance_repo)

    def create_hypothesis_generation_service(
        self,
        session: Session,
    ) -> HypothesisGenerationService:
        dictionary_service = self.create_dictionary_management_service(session)
        relation_repository = SqlAlchemyKernelRelationRepository(session)
        graph_query_service = SqlAlchemyGraphQueryRepository(session)
        registry = get_model_registry()
        model_spec = registry.get_default_model(
            ModelCapability.EVIDENCE_EXTRACTION,
        )
        graph_connection_agent = ArtanaGraphConnectionAdapter(
            model=model_spec.model_id,
            dictionary_service=dictionary_service,
            graph_query_service=graph_query_service,
            relation_repository=relation_repository,
        )
        return HypothesisGenerationService(
            dependencies=HypothesisGenerationServiceDependencies(
                graph_connection_agent=graph_connection_agent,
                relation_claim_service=self.create_kernel_relation_claim_service(
                    session,
                ),
                claim_participant_service=self.create_kernel_claim_participant_service(
                    session,
                ),
                entity_repository=self._build_entity_repository(session),
                relation_repository=relation_repository,
                dictionary_service=dictionary_service,
            ),
        )
