"""Dependencies for kernel (entities/observations/relations/provenance) routes."""

from __future__ import annotations

from fastapi import Depends
from sqlalchemy.orm import Session

from src.application.agents.services.hypothesis_generation_service import (
    HypothesisGenerationService,
)
from src.application.services.kernel import (
    ConceptManagementService,
    DictionaryManagementService,
    KernelClaimEvidenceService,
    KernelClaimParticipantBackfillService,
    KernelClaimParticipantService,
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
from src.database.session import get_session
from src.domain.ports import ConceptPort, DictionaryPort
from src.infrastructure.dependency_injection.dependencies import (
    get_legacy_dependency_container,
)
from src.infrastructure.embeddings import HybridTextEmbeddingProvider
from src.infrastructure.factories.dictionary_search_harness_factory import (
    create_dictionary_search_harness,
)
from src.infrastructure.factories.ingestion_pipeline_factory import (
    create_ingestion_pipeline,
)
from src.infrastructure.ingestion.pipeline import IngestionPipeline
from src.infrastructure.llm.adapters.concept_decision_harness_adapter import (
    DeterministicConceptDecisionHarnessAdapter,
)
from src.infrastructure.repositories.kernel import (
    SqlAlchemyConceptRepository,
    SqlAlchemyDictionaryRepository,
    SqlAlchemyEntityEmbeddingRepository,
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


def _build_entity_repository(session: Session) -> SqlAlchemyKernelEntityRepository:
    enable_phi_encryption = is_phi_encryption_enabled()
    phi_encryption_service = (
        build_phi_encryption_service_from_env() if enable_phi_encryption else None
    )
    return SqlAlchemyKernelEntityRepository(
        session,
        phi_encryption_service=phi_encryption_service,
        enable_phi_encryption=enable_phi_encryption,
    )


def get_dictionary_service(
    session: Session = Depends(get_session),
) -> DictionaryPort:
    """Kernel dictionary service (read/write)."""
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


def get_concept_service(
    session: Session = Depends(get_session),
) -> ConceptPort:
    """Kernel concept manager service (read/write)."""
    concept_repo = SqlAlchemyConceptRepository(session)
    concept_harness = DeterministicConceptDecisionHarnessAdapter()
    return ConceptManagementService(
        concept_repo=concept_repo,
        concept_harness=concept_harness,
    )


def get_kernel_entity_service(
    session: Session = Depends(get_session),
) -> KernelEntityService:
    """Kernel entity CRUD + resolution service."""
    entity_repo = _build_entity_repository(session)
    dictionary_repo = SqlAlchemyDictionaryRepository(session)
    return KernelEntityService(
        entity_repo=entity_repo,
        dictionary_repo=dictionary_repo,
    )


def get_kernel_entity_similarity_service(
    session: Session = Depends(get_session),
) -> KernelEntitySimilarityService:
    """Kernel entity similarity service (hybrid graph + embeddings)."""
    entity_repo = _build_entity_repository(session)
    embedding_repo = SqlAlchemyEntityEmbeddingRepository(session)
    embedding_provider = HybridTextEmbeddingProvider()
    return KernelEntitySimilarityService(
        entity_repo=entity_repo,
        embedding_repo=embedding_repo,
        embedding_provider=embedding_provider,
    )


def get_kernel_observation_service(
    session: Session = Depends(get_session),
) -> KernelObservationService:
    """Kernel observation service (typed fact writes/reads)."""
    observation_repo = SqlAlchemyKernelObservationRepository(session)
    entity_repo = _build_entity_repository(session)
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


def get_kernel_relation_service(
    session: Session = Depends(get_session),
) -> KernelRelationService:
    """Kernel relation service (graph edges + curation lifecycle)."""
    relation_repo = SqlAlchemyKernelRelationRepository(session)
    entity_repo = _build_entity_repository(session)
    return KernelRelationService(
        relation_repo=relation_repo,
        entity_repo=entity_repo,
    )


def get_kernel_relation_suggestion_service(
    session: Session = Depends(get_session),
) -> KernelRelationSuggestionService:
    """Kernel relation suggestion service (dictionary-constrained hybrid scoring)."""
    relation_repo = SqlAlchemyKernelRelationRepository(session)
    entity_repo = _build_entity_repository(session)
    dictionary_repo = SqlAlchemyDictionaryRepository(session)
    embedding_repo = SqlAlchemyEntityEmbeddingRepository(session)
    return KernelRelationSuggestionService(
        entity_repo=entity_repo,
        relation_repo=relation_repo,
        dictionary_repo=dictionary_repo,
        embedding_repo=embedding_repo,
    )


def get_kernel_relation_claim_service(
    session: Session = Depends(get_session),
) -> KernelRelationClaimService:
    """Kernel relation-claim service (claim ledger curation)."""
    relation_claim_repo = SqlAlchemyKernelRelationClaimRepository(session)
    return KernelRelationClaimService(relation_claim_repo=relation_claim_repo)


def get_kernel_relation_projection_source_service(
    session: Session = Depends(get_session),
) -> KernelRelationProjectionSourceService:
    """Kernel relation projection service (claim-backed canonical lineage)."""
    projection_repo = SqlAlchemyKernelRelationProjectionSourceRepository(session)
    return KernelRelationProjectionSourceService(
        relation_projection_repo=projection_repo,
    )


def get_kernel_relation_projection_invariant_service(
    session: Session = Depends(get_session),
) -> KernelRelationProjectionInvariantService:
    """Kernel relation projection invariant service."""
    projection_repo = SqlAlchemyKernelRelationProjectionSourceRepository(session)
    return KernelRelationProjectionInvariantService(
        relation_projection_repo=projection_repo,
    )


def get_kernel_relation_projection_materialization_service(
    session: Session = Depends(get_session),
) -> KernelRelationProjectionMaterializationService:
    """Kernel relation projection materializer."""
    return KernelRelationProjectionMaterializationService(
        relation_repo=SqlAlchemyKernelRelationRepository(session),
        relation_claim_repo=SqlAlchemyKernelRelationClaimRepository(session),
        claim_participant_repo=SqlAlchemyKernelClaimParticipantRepository(session),
        claim_evidence_repo=SqlAlchemyKernelClaimEvidenceRepository(session),
        entity_repo=_build_entity_repository(session),
        dictionary_repo=SqlAlchemyDictionaryRepository(session),
        relation_projection_repo=SqlAlchemyKernelRelationProjectionSourceRepository(
            session,
        ),
    )


def get_kernel_claim_participant_service(
    session: Session = Depends(get_session),
) -> KernelClaimParticipantService:
    """Kernel claim-participant service (structured participant rows)."""
    claim_participant_repo = SqlAlchemyKernelClaimParticipantRepository(session)
    return KernelClaimParticipantService(
        claim_participant_repo=claim_participant_repo,
    )


def get_kernel_claim_participant_backfill_service(
    session: Session = Depends(get_session),
) -> KernelClaimParticipantBackfillService:
    """Backfill/coverage service for structured claim participants."""
    return KernelClaimParticipantBackfillService(
        session=session,
        relation_claim_service=get_kernel_relation_claim_service(session),
        claim_participant_service=get_kernel_claim_participant_service(session),
        entity_repository=_build_entity_repository(session),
        concept_service=get_concept_service(session),
        reasoning_path_service=get_kernel_reasoning_path_service(session),
    )


def get_kernel_claim_relation_service(
    session: Session = Depends(get_session),
) -> KernelClaimRelationService:
    """Kernel claim-relation service (claim-to-claim graph edges)."""
    claim_relation_repo = SqlAlchemyKernelClaimRelationRepository(session)
    return KernelClaimRelationService(
        claim_relation_repo=claim_relation_repo,
    )


def get_kernel_claim_evidence_service(
    session: Session = Depends(get_session),
) -> KernelClaimEvidenceService:
    """Kernel claim-evidence service (claim-level evidence rows)."""
    claim_evidence_repo = SqlAlchemyKernelClaimEvidenceRepository(session)
    return KernelClaimEvidenceService(claim_evidence_repo=claim_evidence_repo)


def get_kernel_graph_view_service(
    session: Session = Depends(get_session),
) -> KernelGraphViewService:
    """Kernel graph view service for domain views and mechanism chains."""
    return KernelGraphViewService(
        KernelGraphViewServiceDependencies(
            entity_service=get_kernel_entity_service(session),
            relation_service=get_kernel_relation_service(session),
            relation_claim_service=get_kernel_relation_claim_service(session),
            claim_participant_service=get_kernel_claim_participant_service(session),
            claim_relation_service=get_kernel_claim_relation_service(session),
            claim_evidence_service=get_kernel_claim_evidence_service(session),
            source_document_repository=SqlAlchemySourceDocumentRepository(session),
        ),
    )


def get_kernel_reasoning_path_service(
    session: Session = Depends(get_session),
) -> KernelReasoningPathService:
    """Derived reasoning-path service for grounded mechanism chains."""
    return KernelReasoningPathService(
        reasoning_path_repo=SqlAlchemyKernelReasoningPathRepository(session),
        relation_claim_service=get_kernel_relation_claim_service(session),
        claim_participant_service=get_kernel_claim_participant_service(session),
        claim_evidence_service=get_kernel_claim_evidence_service(session),
        claim_relation_service=get_kernel_claim_relation_service(session),
        relation_service=get_kernel_relation_service(session),
        session=session,
    )


def get_provenance_service(
    session: Session = Depends(get_session),
) -> ProvenanceService:
    """Kernel provenance service."""
    provenance_repo = SqlAlchemyProvenanceRepository(session)
    return ProvenanceService(provenance_repo=provenance_repo)


def get_ingestion_pipeline(
    session: Session = Depends(get_session),
) -> IngestionPipeline:
    """Fully wired ingestion pipeline (map -> normalize -> resolve -> validate)."""
    return create_ingestion_pipeline(session)


def get_hypothesis_generation_service(
    session: Session = Depends(get_session),
) -> HypothesisGenerationService:
    """Graph-based hypothesis generation service."""
    container = get_legacy_dependency_container()
    return container.create_hypothesis_generation_service(session)


__all__ = [
    "get_concept_service",
    "get_dictionary_service",
    "get_kernel_entity_service",
    "get_kernel_entity_similarity_service",
    "get_kernel_claim_participant_service",
    "get_kernel_claim_participant_backfill_service",
    "get_kernel_claim_relation_service",
    "get_kernel_claim_evidence_service",
    "get_kernel_graph_view_service",
    "get_kernel_relation_projection_source_service",
    "get_kernel_relation_projection_invariant_service",
    "get_kernel_observation_service",
    "get_kernel_reasoning_path_service",
    "get_kernel_relation_service",
    "get_kernel_relation_suggestion_service",
    "get_kernel_relation_claim_service",
    "get_provenance_service",
    "get_ingestion_pipeline",
    "get_hypothesis_generation_service",
]
