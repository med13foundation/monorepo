"""Claim projection service factory mixin."""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.infrastructure.dependency_injection import graph_runtime_factories

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

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
    from src.application.services.kernel.kernel_relation_projection_invariant_service import (
        KernelRelationProjectionInvariantService,
    )
    from src.application.services.kernel.kernel_relation_projection_materialization_service import (
        KernelRelationProjectionMaterializationService,
    )
    from src.application.services.kernel.kernel_relation_projection_source_service import (
        KernelRelationProjectionSourceService,
    )


class KernelClaimProjectionServiceFactoryMixin:
    """Factory methods for claim ledger, evidence, and projection services."""

    def _require_core_factory(self) -> object:
        from src.infrastructure.dependency_injection._kernel_core_service_factories import (
            KernelCoreServiceFactoryMixin,
        )

        if not isinstance(self, KernelCoreServiceFactoryMixin):
            msg = "KernelCoreServiceFactoryMixin is required"
            raise TypeError(msg)
        return self

    def create_kernel_relation_claim_service(
        self,
        session: Session,
    ) -> KernelRelationClaimService:
        core_factory = self._require_core_factory()
        return graph_runtime_factories.create_kernel_relation_claim_service(
            core_factory,
            session,
        )

    def create_kernel_relation_projection_source_service(
        self,
        session: Session,
    ) -> KernelRelationProjectionSourceService:
        core_factory = self._require_core_factory()
        return graph_runtime_factories.create_kernel_relation_projection_source_service(
            core_factory,
            session,
        )

    def create_kernel_relation_projection_invariant_service(
        self,
        session: Session,
    ) -> KernelRelationProjectionInvariantService:
        core_factory = self._require_core_factory()
        return (
            graph_runtime_factories.create_kernel_relation_projection_invariant_service(
                core_factory,
                session,
            )
        )

    def create_kernel_relation_projection_materialization_service(
        self,
        session: Session,
    ) -> KernelRelationProjectionMaterializationService:
        core_factory = self._require_core_factory()
        return graph_runtime_factories.create_kernel_relation_projection_materialization_service(
            core_factory,
            session,
        )

    def create_kernel_claim_participant_service(
        self,
        session: Session,
    ) -> KernelClaimParticipantService:
        core_factory = self._require_core_factory()
        return graph_runtime_factories.create_kernel_claim_participant_service(
            core_factory,
            session,
        )

    def create_kernel_claim_relation_service(
        self,
        session: Session,
    ) -> KernelClaimRelationService:
        core_factory = self._require_core_factory()
        return graph_runtime_factories.create_kernel_claim_relation_service(
            core_factory,
            session,
        )

    def create_kernel_claim_evidence_service(
        self,
        session: Session,
    ) -> KernelClaimEvidenceService:
        core_factory = self._require_core_factory()
        return graph_runtime_factories.create_kernel_claim_evidence_service(
            core_factory,
            session,
        )


__all__ = ["KernelClaimProjectionServiceFactoryMixin"]
