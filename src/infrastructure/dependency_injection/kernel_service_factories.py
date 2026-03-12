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
    KernelClaimParticipantBackfillService,
    KernelClaimParticipantService,
    KernelClaimProjectionReadinessService,
    KernelClaimRelationService,
    KernelEntityService,
    KernelEntitySimilarityService,
    KernelGraphViewService,
    KernelObservationService,
    KernelReasoningPathService,
    KernelRelationClaimService,
    KernelRelationProjectionInvariantService,
    KernelRelationProjectionMaterializationService,
    KernelRelationProjectionSourceService,
    KernelRelationService,
    KernelRelationSuggestionService,
    ProvenanceService,
)
from src.application.services.kernel._kernel_graph_view_support import (
    KernelGraphViewServiceDependencies,
)
from src.domain.agents.models import ModelCapability
from src.infrastructure.embeddings import HybridTextEmbeddingProvider
from src.infrastructure.factories.dictionary_search_harness_factory import (
    create_dictionary_search_harness,
)
from src.infrastructure.llm.adapters import (
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
    SqlAlchemyKernelReasoningPathRepository,
    SqlAlchemyKernelRelationClaimRepository,
    SqlAlchemyKernelRelationProjectionSourceRepository,
    SqlAlchemyKernelRelationRepository,
    SqlAlchemyProvenanceRepository,
)
from src.infrastructure.repositories.source_document_repository import (
    SqlAlchemySourceDocumentRepository,
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
        search_harness = create_dictionary_search_harness(
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
        return KernelRelationService(
            relation_repo=relation_repo,
            entity_repo=entity_repo,
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

    def create_kernel_relation_projection_source_service(
        self,
        session: Session,
    ) -> KernelRelationProjectionSourceService:
        projection_repo = SqlAlchemyKernelRelationProjectionSourceRepository(session)
        return KernelRelationProjectionSourceService(
            relation_projection_repo=projection_repo,
        )

    def create_kernel_relation_projection_invariant_service(
        self,
        session: Session,
    ) -> KernelRelationProjectionInvariantService:
        projection_repo = SqlAlchemyKernelRelationProjectionSourceRepository(session)
        return KernelRelationProjectionInvariantService(
            relation_projection_repo=projection_repo,
        )

    def create_kernel_relation_projection_materialization_service(
        self,
        session: Session,
    ) -> KernelRelationProjectionMaterializationService:
        return KernelRelationProjectionMaterializationService(
            relation_repo=SqlAlchemyKernelRelationRepository(session),
            relation_claim_repo=SqlAlchemyKernelRelationClaimRepository(session),
            claim_participant_repo=SqlAlchemyKernelClaimParticipantRepository(session),
            claim_evidence_repo=SqlAlchemyKernelClaimEvidenceRepository(session),
            entity_repo=self._build_entity_repository(session),
            dictionary_repo=SqlAlchemyDictionaryRepository(session),
            relation_projection_repo=SqlAlchemyKernelRelationProjectionSourceRepository(
                session,
            ),
        )

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

    def create_kernel_graph_view_service(
        self,
        session: Session,
    ) -> KernelGraphViewService:
        return KernelGraphViewService(
            KernelGraphViewServiceDependencies(
                entity_service=self.create_kernel_entity_service(session),
                relation_service=self.create_kernel_relation_service(session),
                relation_claim_service=self.create_kernel_relation_claim_service(
                    session,
                ),
                claim_participant_service=self.create_kernel_claim_participant_service(
                    session,
                ),
                claim_relation_service=self.create_kernel_claim_relation_service(
                    session,
                ),
                claim_evidence_service=self.create_kernel_claim_evidence_service(
                    session,
                ),
                source_document_repository=SqlAlchemySourceDocumentRepository(session),
            ),
        )

    def create_kernel_reasoning_path_service(
        self,
        session: Session,
    ) -> KernelReasoningPathService:
        return KernelReasoningPathService(
            reasoning_path_repo=SqlAlchemyKernelReasoningPathRepository(session),
            relation_claim_service=self.create_kernel_relation_claim_service(session),
            claim_participant_service=self.create_kernel_claim_participant_service(
                session,
            ),
            claim_evidence_service=self.create_kernel_claim_evidence_service(session),
            claim_relation_service=self.create_kernel_claim_relation_service(session),
            relation_service=self.create_kernel_relation_service(session),
            session=session,
        )

    def create_kernel_claim_participant_backfill_service(
        self,
        session: Session,
    ) -> KernelClaimParticipantBackfillService:
        return KernelClaimParticipantBackfillService(
            session=session,
            relation_claim_service=self.create_kernel_relation_claim_service(session),
            claim_participant_service=self.create_kernel_claim_participant_service(
                session,
            ),
            entity_repository=self._build_entity_repository(session),
            concept_service=self.create_concept_management_service(session),
            reasoning_path_service=self.create_kernel_reasoning_path_service(session),
        )

    def create_kernel_claim_projection_readiness_service(
        self,
        session: Session,
    ) -> KernelClaimProjectionReadinessService:
        return KernelClaimProjectionReadinessService(
            session=session,
            relation_projection_invariant_service=(
                self.create_kernel_relation_projection_invariant_service(session)
            ),
            relation_projection_materialization_service=(
                self.create_kernel_relation_projection_materialization_service(session)
            ),
            claim_participant_backfill_service=(
                self.create_kernel_claim_participant_backfill_service(session)
            ),
        )

    def create_dictionary_management_service(
        self,
        session: Session,
    ) -> DictionaryPort:
        dictionary_repo = SqlAlchemyDictionaryRepository(session)
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
                reasoning_path_service=self.create_kernel_reasoning_path_service(
                    session,
                ),
            ),
        )
