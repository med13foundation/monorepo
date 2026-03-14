"""Service-local authz and graph dependency providers."""

from __future__ import annotations

from collections.abc import Callable
from uuid import UUID

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from src.application.agents.services.graph_connection_service import (
    GraphConnectionService,
)
from src.application.agents.services.graph_search_service import GraphSearchService
from src.application.agents.services.hypothesis_generation_service import (
    HypothesisGenerationService,
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
from src.domain.entities.research_space_membership import MembershipRole
from src.domain.entities.user import User
from src.domain.ports import ConceptPort, DictionaryPort
from src.domain.ports.space_access_port import SpaceAccessPort
from src.domain.ports.space_registry_port import SpaceRegistryPort
from src.graph.core.domain_pack import GraphDomainPack
from src.graph.core.feature_flags import FeatureFlagDefinition
from src.graph.core.tenancy import evaluate_graph_tenant_access
from src.graph.core.view_config import GraphViewExtension
from src.graph.runtime import create_graph_domain_pack
from src.infrastructure.dependency_injection.graph_runtime_factories import (
    build_graph_read_model_update_dispatcher,
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
from src.infrastructure.repositories.kernel.kernel_source_document_reference_repository import (
    SqlAlchemyKernelSourceDocumentReferenceRepository,
)
from src.infrastructure.repositories.kernel.kernel_space_access_repository import (
    SqlAlchemyKernelSpaceAccessRepository,
)
from src.infrastructure.repositories.kernel.kernel_space_membership_repository import (
    SqlAlchemyKernelSpaceMembershipRepository,
)
from src.infrastructure.repositories.kernel.kernel_space_registry_repository import (
    SqlAlchemyKernelSpaceRegistryRepository,
)

from .auth import (
    to_graph_access_role,
    to_graph_principal,
    to_graph_rls_session_context,
    to_graph_tenant_membership,
)
from .composition import (
    build_concept_service,
    build_dictionary_repository,
    build_dictionary_service,
    build_entity_repository,
    build_entity_similarity_service,
    build_graph_connection_service,
    build_graph_search_service,
    build_hypothesis_generation_service,
    build_observation_service,
    build_relation_repository,
    build_relation_suggestion_service,
)
from .database import get_session, set_graph_rls_session_context


def get_space_registry_port(
    session: Session = Depends(get_session),
) -> SpaceRegistryPort:
    """Return the graph-local space registry adapter."""
    return SqlAlchemyKernelSpaceRegistryRepository(session)


def get_graph_domain_pack() -> GraphDomainPack:
    """Return the active graph domain pack for the standalone service."""
    return create_graph_domain_pack()


def get_graph_view_extension(
    graph_domain_pack: GraphDomainPack = Depends(get_graph_domain_pack),
) -> GraphViewExtension:
    """Return the active graph view extension."""
    return graph_domain_pack.view_extension


def get_entity_embeddings_flag(
    graph_domain_pack: GraphDomainPack = Depends(get_graph_domain_pack),
) -> FeatureFlagDefinition:
    """Return the active entity-embeddings feature flag."""
    return graph_domain_pack.feature_flags.entity_embeddings


def get_relation_suggestions_flag(
    graph_domain_pack: GraphDomainPack = Depends(get_graph_domain_pack),
) -> FeatureFlagDefinition:
    """Return the active relation-suggestions feature flag."""
    return graph_domain_pack.feature_flags.relation_suggestions


def get_hypothesis_generation_flag(
    graph_domain_pack: GraphDomainPack = Depends(get_graph_domain_pack),
) -> FeatureFlagDefinition:
    """Return the active hypothesis-generation feature flag."""
    return graph_domain_pack.feature_flags.hypothesis_generation


def get_space_membership_repository(
    session: Session = Depends(get_session),
) -> SqlAlchemyKernelSpaceMembershipRepository:
    """Return the graph-local space membership adapter."""
    return SqlAlchemyKernelSpaceMembershipRepository(session)


def get_space_access_port(
    space_registry: SpaceRegistryPort = Depends(get_space_registry_port),
    session: Session = Depends(get_session),
) -> SpaceAccessPort:
    """Return the graph-local space access adapter."""
    return SqlAlchemyKernelSpaceAccessRepository(
        session,
        space_registry=space_registry,
    )


def verify_space_membership(
    *,
    space_id: UUID,
    current_user: User,
    space_access: SpaceAccessPort,
    session: Session,
) -> None:
    """Verify that the caller can access one graph space."""
    principal = to_graph_principal(current_user)
    set_graph_rls_session_context(
        session,
        context=to_graph_rls_session_context(current_user),
    )

    if principal.is_platform_admin:
        return

    membership_role = space_access.get_effective_role(space_id, current_user.id)
    decision = evaluate_graph_tenant_access(
        principal=principal,
        tenant_membership=to_graph_tenant_membership(
            space_id=space_id,
            membership_role=membership_role,
        ),
    )
    if decision.allowed:
        return

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="User is not a member of this graph space",
    )


def require_space_role(
    *,
    space_id: UUID,
    current_user: User,
    space_access: SpaceAccessPort,
    session: Session,
    required_role: MembershipRole,
) -> None:
    """Require one membership role or higher for a graph space."""
    principal = to_graph_principal(current_user)
    set_graph_rls_session_context(
        session,
        context=to_graph_rls_session_context(current_user),
    )

    if principal.is_platform_admin:
        return

    membership_role = space_access.get_effective_role(space_id, current_user.id)
    if membership_role is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User does not have access to this graph space",
        )

    decision = evaluate_graph_tenant_access(
        principal=principal,
        tenant_membership=to_graph_tenant_membership(
            space_id=space_id,
            membership_role=membership_role,
        ),
        required_role=to_graph_access_role(required_role),
    )
    if not decision.allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User lacks permission for this operation",
        )


def get_kernel_entity_service(
    session: Session = Depends(get_session),
    graph_domain_pack: GraphDomainPack = Depends(get_graph_domain_pack),
) -> KernelEntityService:
    """Return kernel entity service bound to the graph service session."""
    return KernelEntityService(
        entity_repo=build_entity_repository(session),
        dictionary_repo=build_dictionary_repository(
            session,
            dictionary_loading_extension=graph_domain_pack.dictionary_loading_extension,
        ),
    )


def get_kernel_entity_similarity_service(
    session: Session = Depends(get_session),
) -> KernelEntitySimilarityService:
    """Return entity similarity service bound to the graph service session."""
    return build_entity_similarity_service(session)


def get_kernel_relation_service(
    session: Session = Depends(get_session),
) -> KernelRelationService:
    """Return kernel relation service bound to the graph service session."""
    return KernelRelationService(
        build_relation_repository(session),
        build_entity_repository(session),
    )


def get_kernel_relation_claim_service(
    session: Session = Depends(get_session),
) -> KernelRelationClaimService:
    """Return kernel relation-claim service."""
    return KernelRelationClaimService(
        relation_claim_repo=SqlAlchemyKernelRelationClaimRepository(session),
        read_model_update_dispatcher=build_graph_read_model_update_dispatcher(session),
    )


def get_kernel_claim_participant_service(
    session: Session = Depends(get_session),
) -> KernelClaimParticipantService:
    """Return kernel claim-participant service."""
    return KernelClaimParticipantService(
        claim_participant_repo=SqlAlchemyKernelClaimParticipantRepository(session),
    )


def get_kernel_relation_projection_source_service(
    session: Session = Depends(get_session),
) -> KernelRelationProjectionSourceService:
    """Return projection-source lineage service."""
    return KernelRelationProjectionSourceService(
        relation_projection_repo=SqlAlchemyKernelRelationProjectionSourceRepository(
            session,
        ),
    )


def get_kernel_claim_relation_service(
    session: Session = Depends(get_session),
) -> KernelClaimRelationService:
    """Return kernel claim-relation service."""
    return KernelClaimRelationService(
        claim_relation_repo=SqlAlchemyKernelClaimRelationRepository(session),
    )


def get_kernel_claim_evidence_service(
    session: Session = Depends(get_session),
) -> KernelClaimEvidenceService:
    """Return kernel claim-evidence service."""
    return KernelClaimEvidenceService(
        claim_evidence_repo=SqlAlchemyKernelClaimEvidenceRepository(session),
    )


def get_kernel_reasoning_path_service(
    session: Session = Depends(get_session),
) -> KernelReasoningPathService:
    """Return reasoning-path service bound to the graph service session."""
    return KernelReasoningPathService(
        reasoning_path_repo=SqlAlchemyKernelReasoningPathRepository(session),
        relation_claim_service=get_kernel_relation_claim_service(session),
        claim_participant_service=get_kernel_claim_participant_service(session),
        claim_evidence_service=get_kernel_claim_evidence_service(session),
        claim_relation_service=get_kernel_claim_relation_service(session),
        relation_service=get_kernel_relation_service(session),
        read_model_update_dispatcher=build_graph_read_model_update_dispatcher(session),
        session=session,
        space_registry_port=SqlAlchemyKernelSpaceRegistryRepository(session),
    )


def get_dictionary_service(
    session: Session = Depends(get_session),
    graph_domain_pack: GraphDomainPack = Depends(get_graph_domain_pack),
) -> DictionaryPort:
    """Return dictionary service bound to the graph service session."""
    return build_dictionary_service(
        session,
        dictionary_loading_extension=graph_domain_pack.dictionary_loading_extension,
    )


def get_kernel_observation_service(
    session: Session = Depends(get_session),
) -> KernelObservationService:
    """Return observation service bound to the graph service session."""
    return build_observation_service(session)


def get_provenance_service(
    session: Session = Depends(get_session),
) -> ProvenanceService:
    """Return provenance service bound to the graph service session."""
    return ProvenanceService(
        provenance_repo=SqlAlchemyProvenanceRepository(session),
    )


def get_concept_service(
    session: Session = Depends(get_session),
) -> ConceptPort:
    """Return concept service bound to the graph service session."""
    return build_concept_service(session)


def get_graph_search_service(
    session: Session = Depends(get_session),
) -> GraphSearchService:
    """Return graph-search service bound to the graph service session."""
    return build_graph_search_service(session)


def get_graph_connection_service(
    session: Session = Depends(get_session),
) -> GraphConnectionService:
    """Return graph-connection service bound to the graph service session."""
    return build_graph_connection_service(session)


def get_kernel_relation_suggestion_service(
    session: Session = Depends(get_session),
) -> KernelRelationSuggestionService:
    """Return relation suggestion service bound to the graph service session."""
    return build_relation_suggestion_service(session)


def get_kernel_relation_projection_materialization_service(
    session: Session = Depends(get_session),
    graph_domain_pack: GraphDomainPack = Depends(get_graph_domain_pack),
) -> KernelRelationProjectionMaterializationService:
    """Return projection materialization service bound to the graph session."""
    return KernelRelationProjectionMaterializationService(
        relation_repo=build_relation_repository(session),
        relation_claim_repo=SqlAlchemyKernelRelationClaimRepository(session),
        claim_participant_repo=SqlAlchemyKernelClaimParticipantRepository(session),
        claim_evidence_repo=SqlAlchemyKernelClaimEvidenceRepository(session),
        entity_repo=build_entity_repository(session),
        dictionary_repo=build_dictionary_repository(
            session,
            dictionary_loading_extension=graph_domain_pack.dictionary_loading_extension,
        ),
        relation_projection_repo=SqlAlchemyKernelRelationProjectionSourceRepository(
            session,
        ),
        read_model_update_dispatcher=build_graph_read_model_update_dispatcher(session),
    )


def get_kernel_graph_view_service(
    session: Session = Depends(get_session),
    graph_domain_pack: GraphDomainPack = Depends(get_graph_domain_pack),
    graph_view_extension: GraphViewExtension = Depends(get_graph_view_extension),
) -> KernelGraphViewService:
    """Return graph-view service bound to the graph service session."""
    from src.application.services.kernel._kernel_graph_view_support import (
        KernelGraphViewServiceDependencies,
    )

    return KernelGraphViewService(
        KernelGraphViewServiceDependencies(
            entity_service=get_kernel_entity_service(
                session,
                graph_domain_pack=graph_domain_pack,
            ),
            relation_service=get_kernel_relation_service(session),
            relation_claim_service=get_kernel_relation_claim_service(session),
            claim_participant_service=get_kernel_claim_participant_service(session),
            claim_relation_service=get_kernel_claim_relation_service(session),
            claim_evidence_service=get_kernel_claim_evidence_service(session),
            source_document_lookup=(
                SqlAlchemyKernelSourceDocumentReferenceRepository(session)
            ),
            view_extension=graph_view_extension,
        ),
    )


def get_kernel_claim_participant_backfill_service(
    session: Session = Depends(get_session),
) -> KernelClaimParticipantBackfillService:
    """Return participant backfill service bound to the graph session."""
    return KernelClaimParticipantBackfillService(
        session=session,
        relation_claim_service=get_kernel_relation_claim_service(session),
        claim_participant_service=get_kernel_claim_participant_service(session),
        entity_repository=build_entity_repository(session),
        concept_service=get_concept_service(session),
        reasoning_path_service=get_kernel_reasoning_path_service(session),
    )


def get_kernel_claim_projection_readiness_service(
    session: Session = Depends(get_session),
    graph_domain_pack: GraphDomainPack = Depends(get_graph_domain_pack),
) -> KernelClaimProjectionReadinessService:
    """Return projection readiness service bound to the graph session."""
    from src.application.services.kernel.kernel_relation_projection_invariant_service import (
        KernelRelationProjectionInvariantService,
    )

    return KernelClaimProjectionReadinessService(
        session=session,
        relation_projection_invariant_service=KernelRelationProjectionInvariantService(
            relation_projection_repo=SqlAlchemyKernelRelationProjectionSourceRepository(
                session,
            ),
        ),
        relation_projection_materialization_service=(
            get_kernel_relation_projection_materialization_service(
                session,
                graph_domain_pack=graph_domain_pack,
            )
        ),
        claim_participant_backfill_service=(
            get_kernel_claim_participant_backfill_service(session)
        ),
    )


def get_hypothesis_generation_service_provider(
    session: Session = Depends(get_session),
) -> Callable[[], HypothesisGenerationService]:
    """Return a lazy hypothesis-generation service provider."""

    def _provider() -> HypothesisGenerationService:
        return build_hypothesis_generation_service(session)

    return _provider


__all__ = [
    "get_concept_service",
    "get_dictionary_service",
    "get_graph_connection_service",
    "get_graph_domain_pack",
    "get_graph_search_service",
    "get_graph_view_extension",
    "get_entity_embeddings_flag",
    "get_hypothesis_generation_service_provider",
    "get_hypothesis_generation_flag",
    "get_kernel_claim_evidence_service",
    "get_kernel_claim_participant_backfill_service",
    "get_kernel_claim_participant_service",
    "get_kernel_claim_projection_readiness_service",
    "get_kernel_claim_relation_service",
    "get_kernel_entity_service",
    "get_kernel_entity_similarity_service",
    "get_kernel_graph_view_service",
    "get_kernel_observation_service",
    "get_kernel_reasoning_path_service",
    "get_kernel_relation_claim_service",
    "get_kernel_relation_projection_materialization_service",
    "get_kernel_relation_projection_source_service",
    "get_kernel_relation_suggestion_service",
    "get_kernel_relation_service",
    "get_relation_suggestions_flag",
    "get_space_access_port",
    "get_provenance_service",
    "require_space_role",
    "verify_space_membership",
]
