"""Claim projection and participant dependency builders."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import Depends
from sqlalchemy.orm import Session

import src.infrastructure.repositories.kernel as kernel_repositories
from src.application.services.kernel.kernel_claim_evidence_service import (
    KernelClaimEvidenceService,
)
from src.application.services.kernel.kernel_claim_participant_service import (
    KernelClaimParticipantService,
)
from src.application.services.kernel.kernel_claim_relation_service import (
    KernelClaimRelationService,
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
from src.database.session import get_session
from src.routes.research_spaces._kernel_dictionary_entity_dependencies import (
    build_entity_repository,
)

if TYPE_CHECKING:
    from src.application.services.kernel.kernel_relation_projection_invariant_service import (
        KernelRelationProjectionInvariantService,
    )


def get_kernel_relation_claim_service(
    session: Session = Depends(get_session),
) -> KernelRelationClaimService:
    return KernelRelationClaimService(
        relation_claim_repo=kernel_repositories.SqlAlchemyKernelRelationClaimRepository(
            session,
        ),
    )


def get_kernel_relation_projection_source_service(
    session: Session = Depends(get_session),
) -> KernelRelationProjectionSourceService:
    return KernelRelationProjectionSourceService(
        relation_projection_repo=kernel_repositories.SqlAlchemyKernelRelationProjectionSourceRepository(
            session,
        ),
    )


def get_kernel_relation_projection_invariant_service(
    session: Session = Depends(get_session),
) -> KernelRelationProjectionInvariantService:
    from src.application.services.kernel.kernel_relation_projection_invariant_service import (
        KernelRelationProjectionInvariantService,
    )

    return KernelRelationProjectionInvariantService(
        relation_projection_repo=kernel_repositories.SqlAlchemyKernelRelationProjectionSourceRepository(
            session,
        ),
    )


def get_kernel_relation_projection_materialization_service(
    session: Session = Depends(get_session),
) -> KernelRelationProjectionMaterializationService:
    return KernelRelationProjectionMaterializationService(
        relation_repo=kernel_repositories.SqlAlchemyKernelRelationRepository(session),
        relation_claim_repo=kernel_repositories.SqlAlchemyKernelRelationClaimRepository(
            session,
        ),
        claim_participant_repo=kernel_repositories.SqlAlchemyKernelClaimParticipantRepository(
            session,
        ),
        claim_evidence_repo=kernel_repositories.SqlAlchemyKernelClaimEvidenceRepository(
            session,
        ),
        entity_repo=build_entity_repository(session),
        dictionary_repo=kernel_repositories.SqlAlchemyDictionaryRepository(session),
        relation_projection_repo=kernel_repositories.SqlAlchemyKernelRelationProjectionSourceRepository(
            session,
        ),
    )


def get_kernel_claim_participant_service(
    session: Session = Depends(get_session),
) -> KernelClaimParticipantService:
    return KernelClaimParticipantService(
        claim_participant_repo=kernel_repositories.SqlAlchemyKernelClaimParticipantRepository(
            session,
        ),
    )


def get_kernel_claim_relation_service(
    session: Session = Depends(get_session),
) -> KernelClaimRelationService:
    return KernelClaimRelationService(
        claim_relation_repo=kernel_repositories.SqlAlchemyKernelClaimRelationRepository(
            session,
        ),
    )


def get_kernel_claim_evidence_service(
    session: Session = Depends(get_session),
) -> KernelClaimEvidenceService:
    return KernelClaimEvidenceService(
        claim_evidence_repo=kernel_repositories.SqlAlchemyKernelClaimEvidenceRepository(
            session,
        ),
    )


__all__ = [
    "get_kernel_claim_evidence_service",
    "get_kernel_claim_participant_service",
    "get_kernel_claim_relation_service",
    "get_kernel_relation_claim_service",
    "get_kernel_relation_projection_invariant_service",
    "get_kernel_relation_projection_materialization_service",
    "get_kernel_relation_projection_source_service",
]
