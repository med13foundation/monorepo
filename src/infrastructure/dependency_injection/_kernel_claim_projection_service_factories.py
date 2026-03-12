"""Claim projection service factory mixin."""

from __future__ import annotations

from typing import TYPE_CHECKING

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

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from src.application.services.kernel.kernel_relation_projection_invariant_service import (
        KernelRelationProjectionInvariantService,
    )
    from src.domain.repositories.kernel.entity_repository import (
        KernelEntityRepository,
    )


class KernelClaimProjectionServiceFactoryMixin:
    """Factory methods for claim ledger, evidence, and projection services."""

    def _require_entity_repository(self, session: Session) -> KernelEntityRepository:
        from src.infrastructure.dependency_injection._kernel_core_service_factories import (
            KernelCoreServiceFactoryMixin,
        )

        if not isinstance(self, KernelCoreServiceFactoryMixin):
            msg = "KernelCoreServiceFactoryMixin is required"
            raise TypeError(msg)
        return self._build_entity_repository(session)

    def create_kernel_relation_claim_service(
        self,
        session: Session,
    ) -> KernelRelationClaimService:
        return KernelRelationClaimService(
            relation_claim_repo=kernel_repositories.SqlAlchemyKernelRelationClaimRepository(
                session,
            ),
        )

    def create_kernel_relation_projection_source_service(
        self,
        session: Session,
    ) -> KernelRelationProjectionSourceService:
        return KernelRelationProjectionSourceService(
            relation_projection_repo=kernel_repositories.SqlAlchemyKernelRelationProjectionSourceRepository(
                session,
            ),
        )

    def create_kernel_relation_projection_invariant_service(
        self,
        session: Session,
    ) -> KernelRelationProjectionInvariantService:
        from src.application.services.kernel.kernel_relation_projection_invariant_service import (
            KernelRelationProjectionInvariantService,
        )

        return KernelRelationProjectionInvariantService(
            relation_projection_repo=kernel_repositories.SqlAlchemyKernelRelationProjectionSourceRepository(
                session,
            ),
        )

    def create_kernel_relation_projection_materialization_service(
        self,
        session: Session,
    ) -> KernelRelationProjectionMaterializationService:
        return KernelRelationProjectionMaterializationService(
            relation_repo=kernel_repositories.SqlAlchemyKernelRelationRepository(
                session,
            ),
            relation_claim_repo=kernel_repositories.SqlAlchemyKernelRelationClaimRepository(
                session,
            ),
            claim_participant_repo=kernel_repositories.SqlAlchemyKernelClaimParticipantRepository(
                session,
            ),
            claim_evidence_repo=kernel_repositories.SqlAlchemyKernelClaimEvidenceRepository(
                session,
            ),
            entity_repo=self._require_entity_repository(session),
            dictionary_repo=kernel_repositories.SqlAlchemyDictionaryRepository(session),
            relation_projection_repo=kernel_repositories.SqlAlchemyKernelRelationProjectionSourceRepository(
                session,
            ),
        )

    def create_kernel_claim_participant_service(
        self,
        session: Session,
    ) -> KernelClaimParticipantService:
        return KernelClaimParticipantService(
            claim_participant_repo=kernel_repositories.SqlAlchemyKernelClaimParticipantRepository(
                session,
            ),
        )

    def create_kernel_claim_relation_service(
        self,
        session: Session,
    ) -> KernelClaimRelationService:
        return KernelClaimRelationService(
            claim_relation_repo=kernel_repositories.SqlAlchemyKernelClaimRelationRepository(
                session,
            ),
        )

    def create_kernel_claim_evidence_service(
        self,
        session: Session,
    ) -> KernelClaimEvidenceService:
        return KernelClaimEvidenceService(
            claim_evidence_repo=kernel_repositories.SqlAlchemyKernelClaimEvidenceRepository(
                session,
            ),
        )


__all__ = ["KernelClaimProjectionServiceFactoryMixin"]
