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
from src.infrastructure.repositories.kernel.kernel_relation_repository import (
    SqlAlchemyKernelRelationRepository,
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

from .auth import is_graph_service_admin
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
    build_relation_suggestion_service,
)
from .database import get_session, set_session_rls_context

_ROLE_HIERARCHY = {
    MembershipRole.VIEWER: 1,
    MembershipRole.RESEARCHER: 2,
    MembershipRole.CURATOR: 3,
    MembershipRole.ADMIN: 4,
    MembershipRole.OWNER: 5,
}


def get_space_registry_port(
    session: Session = Depends(get_session),
) -> SpaceRegistryPort:
    """Return the graph-local space registry adapter."""
    return SqlAlchemyKernelSpaceRegistryRepository(session)


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
    is_admin_user = is_graph_service_admin(current_user)
    set_session_rls_context(
        session,
        current_user_id=current_user.id,
        has_phi_access=is_admin_user,
        is_admin=is_admin_user,
        bypass_rls=False,
    )

    if is_admin_user:
        return

    if space_access.get_effective_role(space_id, current_user.id) is not None:
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
    is_admin_user = is_graph_service_admin(current_user)
    set_session_rls_context(
        session,
        current_user_id=current_user.id,
        has_phi_access=is_admin_user,
        is_admin=is_admin_user,
        bypass_rls=False,
    )

    if is_admin_user:
        return

    membership_role = space_access.get_effective_role(space_id, current_user.id)
    if membership_role is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User does not have access to this graph space",
        )

    if _ROLE_HIERARCHY[membership_role] < _ROLE_HIERARCHY[required_role]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User lacks permission for this operation",
        )


def get_kernel_entity_service(
    session: Session = Depends(get_session),
) -> KernelEntityService:
    """Return kernel entity service bound to the graph service session."""
    return KernelEntityService(
        entity_repo=build_entity_repository(session),
        dictionary_repo=build_dictionary_repository(session),
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
        SqlAlchemyKernelRelationRepository(session),
        build_entity_repository(session),
    )


def get_kernel_relation_claim_service(
    session: Session = Depends(get_session),
) -> KernelRelationClaimService:
    """Return kernel relation-claim service."""
    return KernelRelationClaimService(
        relation_claim_repo=SqlAlchemyKernelRelationClaimRepository(session),
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
        session=session,
        space_registry_port=SqlAlchemyKernelSpaceRegistryRepository(session),
    )


def get_dictionary_service(
    session: Session = Depends(get_session),
) -> DictionaryPort:
    """Return dictionary service bound to the graph service session."""
    return build_dictionary_service(session)


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
) -> KernelRelationProjectionMaterializationService:
    """Return projection materialization service bound to the graph session."""
    return KernelRelationProjectionMaterializationService(
        relation_repo=SqlAlchemyKernelRelationRepository(session),
        relation_claim_repo=SqlAlchemyKernelRelationClaimRepository(session),
        claim_participant_repo=SqlAlchemyKernelClaimParticipantRepository(session),
        claim_evidence_repo=SqlAlchemyKernelClaimEvidenceRepository(session),
        entity_repo=build_entity_repository(session),
        dictionary_repo=build_dictionary_repository(session),
        relation_projection_repo=SqlAlchemyKernelRelationProjectionSourceRepository(
            session,
        ),
    )


def get_kernel_graph_view_service(
    session: Session = Depends(get_session),
) -> KernelGraphViewService:
    """Return graph-view service bound to the graph service session."""
    from src.application.services.kernel._kernel_graph_view_support import (
        KernelGraphViewServiceDependencies,
    )

    return KernelGraphViewService(
        KernelGraphViewServiceDependencies(
            entity_service=get_kernel_entity_service(session),
            relation_service=get_kernel_relation_service(session),
            relation_claim_service=get_kernel_relation_claim_service(session),
            claim_participant_service=get_kernel_claim_participant_service(session),
            claim_relation_service=get_kernel_claim_relation_service(session),
            claim_evidence_service=get_kernel_claim_evidence_service(session),
            source_document_lookup=(
                SqlAlchemyKernelSourceDocumentReferenceRepository(session)
            ),
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
            get_kernel_relation_projection_materialization_service(session)
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
    "get_graph_search_service",
    "get_hypothesis_generation_service_provider",
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
    "get_space_access_port",
    "get_provenance_service",
    "require_space_role",
    "verify_space_membership",
]
