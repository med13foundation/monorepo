# mypy: disable-error-code=no-untyped-def
"""Shared graph runtime builders used by both the service and legacy platform callers."""

from __future__ import annotations

import importlib.util
from typing import TYPE_CHECKING

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
from src.application.services.kernel._kernel_graph_view_support import (
    KernelGraphViewServiceDependencies,
)
from src.application.services.kernel.dictionary_management_service import (
    DictionaryManagementService,
)
from src.application.services.kernel.kernel_claim_evidence_service import (
    KernelClaimEvidenceService,
)
from src.application.services.kernel.kernel_claim_participant_backfill_service import (
    KernelClaimParticipantBackfillService,
)
from src.application.services.kernel.kernel_claim_participant_service import (
    KernelClaimParticipantService,
)
from src.application.services.kernel.kernel_claim_projection_readiness_service import (
    KernelClaimProjectionReadinessService,
)
from src.application.services.kernel.kernel_claim_relation_service import (
    KernelClaimRelationService,
)
from src.application.services.kernel.kernel_entity_claim_summary_projector import (
    KernelEntityClaimSummaryProjector,
)
from src.application.services.kernel.kernel_entity_neighbors_projector import (
    KernelEntityNeighborsProjector,
)
from src.application.services.kernel.kernel_entity_relation_summary_projector import (
    KernelEntityRelationSummaryProjector,
)
from src.application.services.kernel.kernel_entity_service import KernelEntityService
from src.application.services.kernel.kernel_entity_similarity_service import (
    KernelEntitySimilarityService,
)
from src.application.services.kernel.kernel_graph_view_service import (
    KernelGraphViewService,
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
from src.application.services.kernel.kernel_relation_projection_source_service import (
    KernelRelationProjectionSourceService,
)
from src.application.services.kernel.kernel_relation_service import (
    KernelRelationService,
)
from src.application.services.kernel.kernel_relation_suggestion_service import (
    KernelRelationSuggestionService,
)
from src.application.services.kernel.provenance_service import ProvenanceService
from src.application.services.research_query_service import ResearchQueryService
from src.domain.agents.contracts.base import EvidenceItem
from src.domain.agents.contracts.graph_connection import GraphConnectionContract
from src.domain.agents.models import ModelCapability
from src.domain.agents.ports.graph_connection_port import GraphConnectionPort
from src.graph.core.feature_flags import is_flag_enabled
from src.graph.core.read_model import ProjectorBackedGraphReadModelUpdateDispatcher
from src.graph.core.relation_autopromotion_policy import AutoPromotionPolicy
from src.graph.runtime import (
    create_graph_domain_pack,
    create_relation_autopromotion_defaults,
)
from src.infrastructure.embeddings import HybridTextEmbeddingProvider
from src.infrastructure.graph_governance.governance import (
    build_concept_repository as build_graph_concept_repository,
)
from src.infrastructure.graph_governance.governance import (
    build_concept_service as build_graph_concept_service,
)
from src.infrastructure.graph_governance.governance import (
    build_dictionary_repository as build_graph_dictionary_repository,
)
from src.infrastructure.graph_governance.governance import (
    build_dictionary_service as build_graph_dictionary_service,
)
from src.infrastructure.llm.adapters import (
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
from src.infrastructure.repositories.kernel.kernel_provenance_repository import (
    SqlAlchemyProvenanceRepository,
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
from src.infrastructure.repositories.kernel.kernel_relation_repository import (
    SqlAlchemyKernelRelationRepository,
)
from src.infrastructure.repositories.kernel.kernel_source_document_reference_repository import (
    SqlAlchemyKernelSourceDocumentReferenceRepository,
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

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from src.application.services.kernel.kernel_relation_projection_invariant_service import (
        KernelRelationProjectionInvariantService,
    )
    from src.domain.agents.contexts.graph_connection_context import (
        GraphConnectionContext,
    )
    from src.domain.agents.ports.graph_search_port import GraphSearchPort
    from src.domain.ports import ConceptPort, DictionaryPort
    from src.domain.ports.dictionary_search_harness_port import (
        DictionarySearchHarnessPort,
    )
    from src.domain.repositories.kernel.entity_embedding_repository import (
        EntityEmbeddingRepository,
    )
    from src.domain.repositories.kernel.entity_repository import KernelEntityRepository
    from src.domain.repositories.kernel.observation_repository import (
        KernelObservationRepository,
    )
    from src.domain.repositories.kernel.relation_repository import (
        KernelRelationRepository,
    )
    from src.graph.core.domain_pack import GraphDomainPack


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


def build_dictionary_repository(session: Session):
    graph_domain_pack = create_graph_domain_pack()
    return build_graph_dictionary_repository(
        session,
        dictionary_loading_extension=graph_domain_pack.dictionary_loading_extension,
    )


def build_concept_repository(session: Session):
    return build_graph_concept_repository(session)


def build_provenance_repository(session: Session):
    return SqlAlchemyProvenanceRepository(session)


def build_graph_query_repository(session: Session):
    return SqlAlchemyGraphQueryRepository(
        session,
        relation_repository=build_relation_repository(session),
    )


def build_entity_repository(session: Session) -> KernelEntityRepository:
    enable_phi_encryption = is_phi_encryption_enabled()
    phi_encryption_service = (
        build_phi_encryption_service_from_env() if enable_phi_encryption else None
    )
    return SqlAlchemyKernelEntityRepository(
        session,
        phi_encryption_service=phi_encryption_service,
        enable_phi_encryption=enable_phi_encryption,
    )


def build_entity_embedding_repository(
    session: Session,
) -> EntityEmbeddingRepository:
    return SqlAlchemyEntityEmbeddingRepository(session)


def build_observation_repository(
    session: Session,
) -> KernelObservationRepository:
    return SqlAlchemyKernelObservationRepository(session)


def build_relation_autopromotion_policy() -> AutoPromotionPolicy:
    """Resolve relation auto-promotion policy at composition time."""
    return AutoPromotionPolicy.from_environment(
        defaults=create_relation_autopromotion_defaults(),
    )


def build_relation_repository(
    session: Session,
) -> KernelRelationRepository:
    return SqlAlchemyKernelRelationRepository(
        session,
        auto_promotion_policy=build_relation_autopromotion_policy(),
    )


def build_relation_claim_repository(session: Session):
    return SqlAlchemyKernelRelationClaimRepository(session)


def build_relation_projection_source_repository(session: Session):
    return SqlAlchemyKernelRelationProjectionSourceRepository(
        session,
    )


def build_claim_participant_repository(session: Session):
    return SqlAlchemyKernelClaimParticipantRepository(session)


def build_claim_evidence_repository(session: Session):
    return SqlAlchemyKernelClaimEvidenceRepository(session)


def build_claim_relation_repository(session: Session):
    return SqlAlchemyKernelClaimRelationRepository(session)


def build_reasoning_path_repository(session: Session):
    return SqlAlchemyKernelReasoningPathRepository(session)


def build_space_registry_repository(session: Session):
    return SqlAlchemyKernelSpaceRegistryRepository(session)


def build_source_document_reference_repository(session: Session):
    return SqlAlchemyKernelSourceDocumentReferenceRepository(
        session,
    )


def build_dictionary_service(
    session: Session,
    *,
    dictionary_search_harness: DictionarySearchHarnessPort | None = None,
    embedding_provider: HybridTextEmbeddingProvider | None = None,
) -> DictionaryPort:
    graph_domain_pack = create_graph_domain_pack()
    if dictionary_search_harness is None:
        return build_graph_dictionary_service(
            session,
            dictionary_loading_extension=graph_domain_pack.dictionary_loading_extension,
            embedding_provider=embedding_provider,
        )

    active_embedding_provider = embedding_provider or HybridTextEmbeddingProvider()
    dictionary_repo = build_dictionary_repository(session)
    return DictionaryManagementService(
        dictionary_repo=dictionary_repo,
        dictionary_search_harness=dictionary_search_harness,
        embedding_provider=active_embedding_provider,
    )


def create_kernel_entity_service(session: Session) -> KernelEntityService:
    return KernelEntityService(
        entity_repo=build_entity_repository(session),
        dictionary_repo=build_dictionary_repository(session),
    )


def create_kernel_entity_similarity_service(
    session: Session,
) -> KernelEntitySimilarityService:
    return KernelEntitySimilarityService(
        entity_repo=build_entity_repository(session),
        embedding_repo=build_entity_embedding_repository(session),
        embedding_provider=HybridTextEmbeddingProvider(),
    )


def create_kernel_observation_service(
    session: Session,
    *,
    dictionary_service: DictionaryPort | None = None,
    entity_repository: KernelEntityRepository | None = None,
    observation_repository: KernelObservationRepository | None = None,
) -> KernelObservationService:
    return KernelObservationService(
        observation_repo=observation_repository
        or build_observation_repository(session),
        entity_repo=entity_repository or build_entity_repository(session),
        dictionary_repo=dictionary_service
        or create_dictionary_management_service(session),
    )


def create_kernel_relation_service(session: Session) -> KernelRelationService:
    return KernelRelationService(
        relation_repo=build_relation_repository(session),
        entity_repo=build_entity_repository(session),
    )


def create_kernel_relation_suggestion_service(
    session: Session,
) -> KernelRelationSuggestionService:
    graph_domain_pack = create_graph_domain_pack()
    return KernelRelationSuggestionService(
        entity_repo=build_entity_repository(session),
        relation_repo=build_relation_repository(session),
        dictionary_repo=build_dictionary_repository(session),
        embedding_repo=build_entity_embedding_repository(session),
        relation_suggestion_extension=graph_domain_pack.relation_suggestion_extension,
    )


def create_dictionary_management_service(session: Session) -> DictionaryPort:
    return build_dictionary_service(
        session,
        embedding_provider=HybridTextEmbeddingProvider(),
    )


def create_concept_management_service(session: Session) -> ConceptPort:
    return build_graph_concept_service(session)


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


def _build_graph_connection_agent(
    *,
    dictionary_service: DictionaryPort,
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


def build_graph_search_service(session: Session) -> GraphSearchService:
    """Build graph-search orchestration from shared graph runtime factories."""
    graph_domain_pack = create_graph_domain_pack()
    dictionary_service = build_dictionary_service(session)
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


def build_graph_connection_service(session: Session) -> GraphConnectionService:
    """Build graph-connection orchestration from shared graph runtime factories."""
    graph_domain_pack = create_graph_domain_pack()
    dictionary_service = build_dictionary_service(session)
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
            relation_claim_repository=build_relation_claim_repository(session),
            claim_participant_repository=build_claim_participant_repository(session),
            claim_evidence_repository=build_claim_evidence_repository(session),
            relation_projection_source_repository=(
                build_relation_projection_source_repository(session)
            ),
            relation_projection_materialization_service=(
                KernelRelationProjectionMaterializationService(
                    relation_repo=relation_repository,
                    relation_claim_repo=build_relation_claim_repository(session),
                    claim_participant_repo=build_claim_participant_repository(session),
                    claim_evidence_repo=build_claim_evidence_repository(session),
                    entity_repo=build_entity_repository(session),
                    dictionary_repo=build_dictionary_repository(session),
                    relation_projection_repo=build_relation_projection_source_repository(
                        session,
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


def create_provenance_service(session: Session) -> ProvenanceService:
    return ProvenanceService(
        provenance_repo=build_provenance_repository(session),
    )


def create_kernel_relation_claim_service(
    core_factory: object,
    session: Session,
) -> KernelRelationClaimService:
    return KernelRelationClaimService(
        relation_claim_repo=core_factory._build_relation_claim_repository(session),  # type: ignore[attr-defined]  # noqa: SLF001
        read_model_update_dispatcher=build_graph_read_model_update_dispatcher(session),
    )


def create_kernel_relation_projection_source_service(
    core_factory: object,
    session: Session,
) -> KernelRelationProjectionSourceService:
    return KernelRelationProjectionSourceService(
        relation_projection_repo=core_factory._build_relation_projection_source_repository(session),  # type: ignore[attr-defined]  # noqa: SLF001
    )


def create_kernel_relation_projection_invariant_service(
    core_factory: object,
    session: Session,
) -> KernelRelationProjectionInvariantService:
    from src.application.services.kernel.kernel_relation_projection_invariant_service import (
        KernelRelationProjectionInvariantService,
    )

    return KernelRelationProjectionInvariantService(
        relation_projection_repo=core_factory._build_relation_projection_source_repository(session),  # type: ignore[attr-defined]  # noqa: SLF001
    )


def create_kernel_relation_projection_materialization_service(
    core_factory: object,
    session: Session,
) -> KernelRelationProjectionMaterializationService:
    return KernelRelationProjectionMaterializationService(
        relation_repo=core_factory._build_relation_repository(session),  # type: ignore[attr-defined]  # noqa: SLF001
        relation_claim_repo=core_factory._build_relation_claim_repository(session),  # type: ignore[attr-defined]  # noqa: SLF001
        claim_participant_repo=core_factory._build_claim_participant_repository(session),  # type: ignore[attr-defined]  # noqa: SLF001
        claim_evidence_repo=core_factory._build_claim_evidence_repository(session),  # type: ignore[attr-defined]  # noqa: SLF001
        entity_repo=core_factory._build_entity_repository(session),  # type: ignore[attr-defined]  # noqa: SLF001
        dictionary_repo=core_factory._build_dictionary_repository(session),  # type: ignore[attr-defined]  # noqa: SLF001
        relation_projection_repo=core_factory._build_relation_projection_source_repository(session),  # type: ignore[attr-defined]  # noqa: SLF001
        read_model_update_dispatcher=build_graph_read_model_update_dispatcher(session),
    )


def build_graph_read_model_update_dispatcher(
    session: Session,
) -> ProjectorBackedGraphReadModelUpdateDispatcher:
    """Build the current read-model dispatcher runtime adapter."""
    from src.application.services.kernel.kernel_entity_mechanism_paths_projector import (
        KernelEntityMechanismPathsProjector,
    )

    entity_claim_summary_projector = KernelEntityClaimSummaryProjector(session)
    entity_mechanism_paths_projector = KernelEntityMechanismPathsProjector(session)
    entity_neighbors_projector = KernelEntityNeighborsProjector(session)
    entity_relation_summary_projector = KernelEntityRelationSummaryProjector(session)
    return ProjectorBackedGraphReadModelUpdateDispatcher(
        projectors={
            entity_claim_summary_projector.definition.name: (
                entity_claim_summary_projector
            ),
            entity_mechanism_paths_projector.definition.name: (
                entity_mechanism_paths_projector
            ),
            entity_neighbors_projector.definition.name: entity_neighbors_projector,
            entity_relation_summary_projector.definition.name: (
                entity_relation_summary_projector
            ),
        },
    )


def create_kernel_claim_participant_service(
    core_factory: object,
    session: Session,
) -> KernelClaimParticipantService:
    return KernelClaimParticipantService(
        claim_participant_repo=core_factory._build_claim_participant_repository(session),  # type: ignore[attr-defined]  # noqa: SLF001
    )


def create_kernel_claim_relation_service(
    core_factory: object,
    session: Session,
) -> KernelClaimRelationService:
    return KernelClaimRelationService(
        claim_relation_repo=core_factory._build_claim_relation_repository(session),  # type: ignore[attr-defined]  # noqa: SLF001
    )


def create_kernel_claim_evidence_service(
    core_factory: object,
    session: Session,
) -> KernelClaimEvidenceService:
    return KernelClaimEvidenceService(
        claim_evidence_repo=core_factory._build_claim_evidence_repository(session),  # type: ignore[attr-defined]  # noqa: SLF001
    )


def create_kernel_graph_view_service(
    core_factory: object,
    projection_factory: object,
    session: Session,
) -> KernelGraphViewService:
    graph_domain_pack = create_graph_domain_pack()
    return KernelGraphViewService(
        KernelGraphViewServiceDependencies(
            entity_service=core_factory.create_kernel_entity_service(session),  # type: ignore[attr-defined]
            relation_service=core_factory.create_kernel_relation_service(session),  # type: ignore[attr-defined]
            relation_claim_service=projection_factory.create_kernel_relation_claim_service(session),  # type: ignore[attr-defined]
            claim_participant_service=projection_factory.create_kernel_claim_participant_service(session),  # type: ignore[attr-defined]
            claim_relation_service=projection_factory.create_kernel_claim_relation_service(session),  # type: ignore[attr-defined]
            claim_evidence_service=projection_factory.create_kernel_claim_evidence_service(session),  # type: ignore[attr-defined]
            source_document_lookup=core_factory._build_source_document_reference_repository(session),  # type: ignore[attr-defined]  # noqa: SLF001
            view_extension=graph_domain_pack.view_extension,
        ),
    )


def create_kernel_reasoning_path_service(
    core_factory: object,
    projection_factory: object,
    session: Session,
) -> KernelReasoningPathService:
    return KernelReasoningPathService(
        reasoning_path_repo=core_factory._build_reasoning_path_repository(session),  # type: ignore[attr-defined]  # noqa: SLF001
        relation_claim_service=projection_factory.create_kernel_relation_claim_service(session),  # type: ignore[attr-defined]
        claim_participant_service=projection_factory.create_kernel_claim_participant_service(session),  # type: ignore[attr-defined]
        claim_evidence_service=projection_factory.create_kernel_claim_evidence_service(session),  # type: ignore[attr-defined]
        claim_relation_service=projection_factory.create_kernel_claim_relation_service(session),  # type: ignore[attr-defined]
        relation_service=core_factory.create_kernel_relation_service(session),  # type: ignore[attr-defined]
        read_model_update_dispatcher=build_graph_read_model_update_dispatcher(session),
        session=session,
        space_registry_port=core_factory._build_space_registry_repository(session),  # type: ignore[attr-defined]  # noqa: SLF001
    )


def create_kernel_claim_participant_backfill_service(
    core_factory: object,
    projection_factory: object,
    session: Session,
) -> KernelClaimParticipantBackfillService:
    return KernelClaimParticipantBackfillService(
        session=session,
        relation_claim_service=projection_factory.create_kernel_relation_claim_service(session),  # type: ignore[attr-defined]
        claim_participant_service=projection_factory.create_kernel_claim_participant_service(session),  # type: ignore[attr-defined]
        entity_repository=core_factory._build_entity_repository(session),  # type: ignore[attr-defined]  # noqa: SLF001
        concept_service=core_factory.create_concept_management_service(session),  # type: ignore[attr-defined]
        reasoning_path_service=create_kernel_reasoning_path_service(
            core_factory,
            projection_factory,
            session,
        ),
    )


def create_kernel_claim_projection_readiness_service(
    projection_factory: object,
    session: Session,
) -> KernelClaimProjectionReadinessService:
    return KernelClaimProjectionReadinessService(
        session=session,
        relation_projection_invariant_service=projection_factory.create_kernel_relation_projection_invariant_service(session),  # type: ignore[attr-defined]
        relation_projection_materialization_service=projection_factory.create_kernel_relation_projection_materialization_service(session),  # type: ignore[attr-defined]
        claim_participant_backfill_service=projection_factory.create_kernel_claim_participant_backfill_service(session),  # type: ignore[attr-defined]
    )


def create_hypothesis_generation_service(
    core_factory: object,
    projection_factory: object,
    session: Session,
) -> HypothesisGenerationService:
    dictionary_service = core_factory.create_dictionary_management_service(session)  # type: ignore[attr-defined]
    graph_domain_pack = create_graph_domain_pack()
    relation_repository = core_factory._build_relation_repository(session)  # type: ignore[attr-defined]  # noqa: SLF001
    graph_query_service = core_factory._build_graph_query_repository(session)  # type: ignore[attr-defined]  # noqa: SLF001
    model_spec = get_model_registry().get_default_model(
        ModelCapability.EVIDENCE_EXTRACTION,
    )
    graph_connection_agent = ArtanaGraphConnectionAdapter(
        model=model_spec.model_id,
        prompt_config=graph_domain_pack.graph_connection_prompt,
        dictionary_service=dictionary_service,
        graph_query_service=graph_query_service,
        relation_repository=relation_repository,
    )
    return HypothesisGenerationService(
        dependencies=HypothesisGenerationServiceDependencies(
            graph_connection_agent=graph_connection_agent,
            relation_claim_service=projection_factory.create_kernel_relation_claim_service(session),  # type: ignore[attr-defined]
            claim_participant_service=projection_factory.create_kernel_claim_participant_service(session),  # type: ignore[attr-defined]
            claim_evidence_service=projection_factory.create_kernel_claim_evidence_service(session),  # type: ignore[attr-defined]
            entity_repository=core_factory._build_entity_repository(session),  # type: ignore[attr-defined]  # noqa: SLF001
            relation_repository=relation_repository,
            dictionary_service=dictionary_service,
            reasoning_path_service=create_kernel_reasoning_path_service(
                core_factory,
                projection_factory,
                session,
            ),
        ),
    )


__all__ = [
    "build_claim_evidence_repository",
    "build_claim_participant_repository",
    "build_claim_relation_repository",
    "build_concept_repository",
    "build_dictionary_repository",
    "build_dictionary_service",
    "build_entity_embedding_repository",
    "build_entity_repository",
    "build_graph_read_model_update_dispatcher",
    "build_graph_query_repository",
    "build_observation_repository",
    "build_provenance_repository",
    "build_reasoning_path_repository",
    "build_relation_autopromotion_policy",
    "build_relation_claim_repository",
    "build_relation_projection_source_repository",
    "build_relation_repository",
    "build_source_document_reference_repository",
    "build_space_registry_repository",
    "create_concept_management_service",
    "create_dictionary_management_service",
    "create_hypothesis_generation_service",
    "create_kernel_claim_evidence_service",
    "create_kernel_claim_participant_backfill_service",
    "create_kernel_claim_participant_service",
    "create_kernel_claim_projection_readiness_service",
    "create_kernel_claim_relation_service",
    "create_kernel_entity_service",
    "create_kernel_entity_similarity_service",
    "create_kernel_graph_view_service",
    "create_kernel_observation_service",
    "create_kernel_reasoning_path_service",
    "create_kernel_relation_claim_service",
    "create_kernel_relation_projection_invariant_service",
    "create_kernel_relation_projection_materialization_service",
    "create_kernel_relation_projection_source_service",
    "create_kernel_relation_service",
    "create_kernel_relation_suggestion_service",
    "create_provenance_service",
]
