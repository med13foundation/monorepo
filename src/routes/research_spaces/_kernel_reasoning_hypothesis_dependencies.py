"""Reasoning, graph-view, readiness, and hypothesis dependency builders."""

from __future__ import annotations

from fastapi import Depends
from sqlalchemy.orm import Session

import src.infrastructure.repositories.kernel as kernel_repositories
from src.application.agents.services.hypothesis_generation_service import (
    HypothesisGenerationService,
)
from src.application.services.kernel.kernel_claim_participant_backfill_service import (
    KernelClaimParticipantBackfillService,
)
from src.application.services.kernel.kernel_claim_projection_readiness_service import (
    KernelClaimProjectionReadinessService,
)
from src.application.services.kernel.kernel_graph_view_service import (
    KernelGraphViewService,
)
from src.application.services.kernel.kernel_reasoning_path_service import (
    KernelReasoningPathService,
)
from src.database.session import get_session
from src.infrastructure.dependency_injection.dependencies import (
    get_legacy_dependency_container,
)
from src.infrastructure.repositories.source_document_repository import (
    SqlAlchemySourceDocumentRepository,
)
from src.routes.research_spaces._kernel_claim_projection_dependencies import (
    get_kernel_claim_evidence_service,
    get_kernel_claim_participant_service,
    get_kernel_claim_relation_service,
    get_kernel_relation_claim_service,
    get_kernel_relation_projection_invariant_service,
    get_kernel_relation_projection_materialization_service,
)
from src.routes.research_spaces._kernel_dictionary_entity_dependencies import (
    build_entity_repository,
    get_concept_service,
    get_kernel_entity_service,
)
from src.routes.research_spaces._kernel_graph_operation_dependencies import (
    get_kernel_relation_service,
)


def get_kernel_graph_view_service(
    session: Session = Depends(get_session),
) -> KernelGraphViewService:
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
            source_document_repository=SqlAlchemySourceDocumentRepository(session),
        ),
    )


def get_kernel_reasoning_path_service(
    session: Session = Depends(get_session),
) -> KernelReasoningPathService:
    return KernelReasoningPathService(
        reasoning_path_repo=kernel_repositories.SqlAlchemyKernelReasoningPathRepository(
            session,
        ),
        relation_claim_service=get_kernel_relation_claim_service(session),
        claim_participant_service=get_kernel_claim_participant_service(session),
        claim_evidence_service=get_kernel_claim_evidence_service(session),
        claim_relation_service=get_kernel_claim_relation_service(session),
        relation_service=get_kernel_relation_service(session),
        session=session,
    )


def get_kernel_claim_participant_backfill_service(
    session: Session = Depends(get_session),
) -> KernelClaimParticipantBackfillService:
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
    return KernelClaimProjectionReadinessService(
        session=session,
        relation_projection_invariant_service=(
            get_kernel_relation_projection_invariant_service(session)
        ),
        relation_projection_materialization_service=(
            get_kernel_relation_projection_materialization_service(session)
        ),
        claim_participant_backfill_service=(
            get_kernel_claim_participant_backfill_service(session)
        ),
    )


def get_hypothesis_generation_service(
    session: Session = Depends(get_session),
) -> HypothesisGenerationService:
    return get_legacy_dependency_container().create_hypothesis_generation_service(
        session,
    )


__all__ = [
    "get_hypothesis_generation_service",
    "get_kernel_claim_participant_backfill_service",
    "get_kernel_claim_projection_readiness_service",
    "get_kernel_graph_view_service",
    "get_kernel_reasoning_path_service",
]
