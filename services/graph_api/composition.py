"""Service-local composition helpers for the standalone graph API."""

from __future__ import annotations

import importlib.util

from sqlalchemy.orm import Session

from src.application.agents.services import (
    GovernanceService,
    GraphConnectionService,
    GraphConnectionServiceDependencies,
    GraphSearchService,
    GraphSearchServiceDependencies,
)
from src.application.agents.services.hypothesis_generation_service import (
    HypothesisGenerationService,
    HypothesisGenerationServiceDependencies,
)
from src.application.services.kernel.kernel_claim_evidence_service import (
    KernelClaimEvidenceService,
)
from src.application.services.kernel.kernel_claim_participant_service import (
    KernelClaimParticipantService,
)
from src.application.services.kernel.kernel_claim_relation_service import (
    KernelClaimRelationService,
)
from src.application.services.kernel.kernel_entity_similarity_service import (
    KernelEntitySimilarityService,
)
from src.application.services.kernel.kernel_observation_service import (
    KernelObservationService,
)
from src.application.services.kernel.kernel_reasoning_path_service import (
    KernelReasoningPathService,
)
from src.application.services.kernel.kernel_relation_claim_service import (
    KernelRelationClaimService,
)
from src.application.services.kernel.kernel_relation_projection_materialization_service import (
    KernelRelationProjectionMaterializationService,
)
from src.application.services.kernel.kernel_relation_service import (
    KernelRelationService,
)
from src.application.services.kernel.kernel_relation_suggestion_service import (
    KernelRelationSuggestionService,
)
from src.application.services.research_query_service import ResearchQueryService
from src.domain.agents.contexts.graph_connection_context import GraphConnectionContext
from src.domain.agents.contracts.base import EvidenceItem
from src.domain.agents.contracts.graph_connection import GraphConnectionContract
from src.domain.agents.models import ModelCapability
from src.domain.agents.ports.graph_connection_port import GraphConnectionPort
from src.domain.agents.ports.graph_search_port import GraphSearchPort
from src.domain.repositories.kernel.entity_repository import KernelEntityRepository
from src.domain.repositories.kernel.relation_repository import KernelRelationRepository
from src.graph.core.domain_pack import GraphDomainPack
from src.graph.core.feature_flags import is_flag_enabled
from src.graph.runtime import create_graph_domain_pack
from src.infrastructure.dependency_injection.graph_runtime_factories import (
    build_graph_query_repository,
    build_graph_read_model_update_dispatcher,
    build_relation_repository,
)
from src.infrastructure.embeddings import HybridTextEmbeddingProvider
from src.infrastructure.llm.adapters.graph_connection_agent_adapter import (
    ArtanaGraphConnectionAdapter,
)
from src.infrastructure.llm.adapters.graph_search_agent_adapter import (
    ArtanaGraphSearchAdapter,
)
from src.infrastructure.llm.config.model_registry import get_model_registry
from src.infrastructure.repositories.kernel.graph_query_repository import (
    SqlAlchemyGraphQueryRepository,
)
from src.infrastructure.repositories.kernel.kernel_claim_evidence_repository import (
    SqlAlchemyKernelClaimEvidenceRepository,
)
from src.infrastructure.repositories.kernel.kernel_claim_participant_repository import (
    SqlAlchemyKernelClaimParticipantRepository,
)
from src.infrastructure.repositories.kernel.kernel_claim_relation_repository import (
    SqlAlchemyKernelClaimRelationRepository,
)
from src.infrastructure.repositories.kernel.kernel_entity_embedding_repository import (
    SqlAlchemyEntityEmbeddingRepository,
)
from src.infrastructure.repositories.kernel.kernel_entity_repository import (
    SqlAlchemyKernelEntityRepository,
)
from src.infrastructure.repositories.kernel.kernel_observation_repository import (
    SqlAlchemyKernelObservationRepository,
)
from src.infrastructure.repositories.kernel.kernel_reasoning_path_repository import (
    SqlAlchemyKernelReasoningPathRepository,
)
from src.infrastructure.repositories.kernel.kernel_relation_claim_repository import (
    SqlAlchemyKernelRelationClaimRepository,
)
from src.infrastructure.repositories.kernel.kernel_relation_projection_source_repository import (
    SqlAlchemyKernelRelationProjectionSourceRepository,
)
from src.infrastructure.repositories.kernel.kernel_space_registry_repository import (
    SqlAlchemyKernelSpaceRegistryRepository,
)
from src.infrastructure.repositories.kernel.kernel_space_settings_repository import (
    SqlAlchemyKernelSpaceSettingsRepository,
)
from src.infrastructure.security.phi_encryption import (
    build_phi_encryption_service_from_env,
    is_phi_encryption_enabled,
)

from .governance import (
    build_concept_service,
    build_dictionary_repository,
    build_dictionary_service,
)


class _UnavailableGraphConnectionAgent(GraphConnectionPort):
    """Fallback graph-connection agent when Artana is unavailable."""

    def __init__(self, reason: str) -> None:
        self._reason = reason

    async def discover(
        self,
        context: GraphConnectionContext,
        *,
        model_id: str | None = None,
    ) -> GraphConnectionContract:
        del model_id
        return GraphConnectionContract(
            decision="fallback",
            confidence_score=0.05,
            rationale=f"Graph connection agent unavailable ({self._reason}).",
            evidence=[
                EvidenceItem(
                    source_type="note",
                    locator=f"graph-connection:{context.research_space_id}",
                    excerpt=f"Unavailable reason: {self._reason}",
                    relevance=0.1,
                ),
            ],
            source_type=context.source_type,
            research_space_id=context.research_space_id,
            seed_entity_id=context.seed_entity_id,
            proposed_relations=[],
            rejected_candidates=[],
            shadow_mode=context.shadow_mode,
            agent_run_id=None,
        )

    async def close(self) -> None:
        return None


def build_entity_repository(session: Session) -> KernelEntityRepository:
    """Build the graph-service entity repository with local security wiring."""
    enable_phi_encryption = is_phi_encryption_enabled()
    phi_encryption_service = (
        build_phi_encryption_service_from_env() if enable_phi_encryption else None
    )
    return SqlAlchemyKernelEntityRepository(
        session,
        phi_encryption_service=phi_encryption_service,
        enable_phi_encryption=enable_phi_encryption,
    )


def build_entity_similarity_service(
    session: Session,
) -> KernelEntitySimilarityService:
    """Build the graph-service hybrid entity similarity service."""
    return KernelEntitySimilarityService(
        entity_repo=build_entity_repository(session),
        embedding_repo=SqlAlchemyEntityEmbeddingRepository(session),
        embedding_provider=HybridTextEmbeddingProvider(),
    )


def _build_graph_search_agent(
    *,
    graph_query_service: object,
    graph_domain_pack: GraphDomainPack,
) -> GraphSearchPort | None:
    if not is_flag_enabled(graph_domain_pack.feature_flags.search_agent):
        return None
    if importlib.util.find_spec("artana") is None:
        return None

    registry = get_model_registry()
    model_spec = registry.get_default_model(ModelCapability.QUERY_GENERATION)
    try:
        return ArtanaGraphSearchAdapter(
            model=model_spec.model_id,
            search_extension=graph_domain_pack.search_extension,
            graph_query_service=graph_query_service,
        )
    except Exception:  # noqa: BLE001 - preserve API availability
        return None


def build_graph_search_service(session: Session) -> GraphSearchService:
    """Build the graph-service graph-search orchestration service."""
    graph_domain_pack = create_graph_domain_pack()
    dictionary_service = build_dictionary_service(
        session,
        dictionary_loading_extension=graph_domain_pack.dictionary_loading_extension,
    )
    graph_query_service = build_graph_query_repository(session)
    return GraphSearchService(
        dependencies=GraphSearchServiceDependencies(
            research_query_service=ResearchQueryService(
                dictionary_service=dictionary_service,
            ),
            graph_query_service=graph_query_service,
            graph_search_agent=_build_graph_search_agent(
                graph_query_service=graph_query_service,
                graph_domain_pack=graph_domain_pack,
            ),
            governance_service=GovernanceService(),
        ),
    )


def _build_graph_connection_agent(
    *,
    dictionary_service: object,
    graph_query_service: SqlAlchemyGraphQueryRepository,
    relation_repository: KernelRelationRepository,
    graph_domain_pack: GraphDomainPack,
) -> GraphConnectionPort:
    registry = get_model_registry()
    model_spec = registry.get_default_model(ModelCapability.EVIDENCE_EXTRACTION)
    try:
        return ArtanaGraphConnectionAdapter(
            model=model_spec.model_id,
            prompt_config=graph_domain_pack.graph_connection_prompt,
            dictionary_service=dictionary_service,
            graph_query_service=graph_query_service,
            relation_repository=relation_repository,
        )
    except Exception as exc:  # noqa: BLE001 - preserve API availability
        return _UnavailableGraphConnectionAgent(str(exc))


def build_graph_connection_service(session: Session) -> GraphConnectionService:
    """Build the graph-service graph-connection orchestration service."""
    graph_domain_pack = create_graph_domain_pack()
    dictionary_service = build_dictionary_service(
        session,
        dictionary_loading_extension=graph_domain_pack.dictionary_loading_extension,
    )
    relation_repository = build_relation_repository(session)
    graph_query_service = build_graph_query_repository(session)
    graph_connection_agent = _build_graph_connection_agent(
        dictionary_service=dictionary_service,
        graph_query_service=graph_query_service,
        relation_repository=relation_repository,
        graph_domain_pack=graph_domain_pack,
    )

    return GraphConnectionService(
        dependencies=GraphConnectionServiceDependencies(
            graph_connection_agent=graph_connection_agent,
            graph_connection_prompt=graph_domain_pack.graph_connection_prompt,
            relation_repository=relation_repository,
            entity_repository=build_entity_repository(session),
            relation_claim_repository=SqlAlchemyKernelRelationClaimRepository(
                session,
            ),
            claim_participant_repository=(
                SqlAlchemyKernelClaimParticipantRepository(session)
            ),
            claim_evidence_repository=SqlAlchemyKernelClaimEvidenceRepository(
                session,
            ),
            relation_projection_source_repository=(
                SqlAlchemyKernelRelationProjectionSourceRepository(
                    session,
                )
            ),
            relation_projection_materialization_service=(
                KernelRelationProjectionMaterializationService(
                    relation_repo=relation_repository,
                    relation_claim_repo=SqlAlchemyKernelRelationClaimRepository(
                        session,
                    ),
                    claim_participant_repo=(
                        SqlAlchemyKernelClaimParticipantRepository(
                            session,
                        )
                    ),
                    claim_evidence_repo=(
                        SqlAlchemyKernelClaimEvidenceRepository(
                            session,
                        )
                    ),
                    entity_repo=build_entity_repository(session),
                    dictionary_repo=build_dictionary_repository(
                        session,
                        dictionary_loading_extension=(
                            graph_domain_pack.dictionary_loading_extension
                        ),
                    ),
                    relation_projection_repo=(
                        SqlAlchemyKernelRelationProjectionSourceRepository(
                            session,
                        )
                    ),
                    read_model_update_dispatcher=(
                        build_graph_read_model_update_dispatcher(session)
                    ),
                )
            ),
            governance_service=GovernanceService(),
            space_settings_port=SqlAlchemyKernelSpaceSettingsRepository(session),
            rollback_on_error=session.rollback,
        ),
    )


def build_hypothesis_generation_service(
    session: Session,
) -> HypothesisGenerationService:
    """Build the graph-service hypothesis orchestration service locally."""
    graph_domain_pack = create_graph_domain_pack()
    dictionary_service = build_dictionary_service(
        session,
        dictionary_loading_extension=graph_domain_pack.dictionary_loading_extension,
    )
    relation_repository = build_relation_repository(session)
    graph_query_service = build_graph_query_repository(session)
    graph_connection_agent = _build_graph_connection_agent(
        dictionary_service=dictionary_service,
        graph_query_service=graph_query_service,
        relation_repository=relation_repository,
        graph_domain_pack=graph_domain_pack,
    )
    relation_claim_service = KernelRelationClaimService(
        relation_claim_repo=SqlAlchemyKernelRelationClaimRepository(session),
        read_model_update_dispatcher=build_graph_read_model_update_dispatcher(session),
    )
    claim_participant_service = KernelClaimParticipantService(
        claim_participant_repo=SqlAlchemyKernelClaimParticipantRepository(session),
    )
    claim_evidence_service = KernelClaimEvidenceService(
        claim_evidence_repo=SqlAlchemyKernelClaimEvidenceRepository(session),
    )
    claim_relation_service = KernelClaimRelationService(
        claim_relation_repo=SqlAlchemyKernelClaimRelationRepository(session),
    )
    relation_service = KernelRelationService(
        relation_repo=relation_repository,
        entity_repo=build_entity_repository(session),
    )
    reasoning_path_service = KernelReasoningPathService(
        reasoning_path_repo=SqlAlchemyKernelReasoningPathRepository(session),
        relation_claim_service=relation_claim_service,
        claim_participant_service=claim_participant_service,
        claim_evidence_service=claim_evidence_service,
        claim_relation_service=claim_relation_service,
        relation_service=relation_service,
        read_model_update_dispatcher=build_graph_read_model_update_dispatcher(session),
        session=session,
        space_registry_port=SqlAlchemyKernelSpaceRegistryRepository(session),
    )
    return HypothesisGenerationService(
        dependencies=HypothesisGenerationServiceDependencies(
            graph_connection_agent=graph_connection_agent,
            relation_claim_service=relation_claim_service,
            claim_participant_service=claim_participant_service,
            claim_evidence_service=claim_evidence_service,
            entity_repository=build_entity_repository(session),
            relation_repository=relation_repository,
            dictionary_service=dictionary_service,
            reasoning_path_service=reasoning_path_service,
        ),
    )


def build_observation_service(
    session: Session,
) -> KernelObservationService:
    """Build the graph-service observation service."""
    graph_domain_pack = create_graph_domain_pack()
    return KernelObservationService(
        observation_repo=SqlAlchemyKernelObservationRepository(
            session,
        ),
        entity_repo=build_entity_repository(session),
        dictionary_repo=build_dictionary_service(
            session,
            dictionary_loading_extension=graph_domain_pack.dictionary_loading_extension,
        ),
    )


def build_relation_suggestion_service(
    session: Session,
) -> KernelRelationSuggestionService:
    """Build the graph-service hybrid relation suggestion service."""
    graph_domain_pack = create_graph_domain_pack()
    return KernelRelationSuggestionService(
        entity_repo=build_entity_repository(session),
        relation_repo=build_relation_repository(session),
        dictionary_repo=build_dictionary_repository(
            session,
            dictionary_loading_extension=graph_domain_pack.dictionary_loading_extension,
        ),
        embedding_repo=SqlAlchemyEntityEmbeddingRepository(session),
        relation_suggestion_extension=graph_domain_pack.relation_suggestion_extension,
    )


__all__ = [
    "build_graph_connection_service",
    "build_hypothesis_generation_service",
    "build_graph_search_service",
    "build_concept_service",
    "build_dictionary_repository",
    "build_dictionary_service",
    "build_entity_repository",
    "build_entity_similarity_service",
    "build_observation_service",
    "build_relation_repository",
    "build_relation_suggestion_service",
]
