"""Reasoning, readiness, and hypothesis service factory mixin."""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.infrastructure.dependency_injection import graph_runtime_factories

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

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


class KernelReasoningHypothesisServiceFactoryMixin:
    """Factory methods for reasoning paths, graph views, readiness, and hypotheses."""

    def _require_core_factory(self) -> object:
        from src.infrastructure.dependency_injection._kernel_core_service_factories import (
            KernelCoreServiceFactoryMixin,
        )

        if not isinstance(self, KernelCoreServiceFactoryMixin):
            msg = "KernelCoreServiceFactoryMixin is required"
            raise TypeError(msg)
        return self

    def _require_projection_factory(self) -> object:
        from src.infrastructure.dependency_injection._kernel_claim_projection_service_factories import (
            KernelClaimProjectionServiceFactoryMixin,
        )

        if not isinstance(self, KernelClaimProjectionServiceFactoryMixin):
            msg = "KernelClaimProjectionServiceFactoryMixin is required"
            raise TypeError(msg)
        return self

    def create_kernel_graph_view_service(
        self,
        session: Session,
    ) -> KernelGraphViewService:
        core_factory = self._require_core_factory()
        projection_factory = self._require_projection_factory()
        return graph_runtime_factories.create_kernel_graph_view_service(
            core_factory,
            projection_factory,
            session,
        )

    def create_kernel_reasoning_path_service(
        self,
        session: Session,
    ) -> KernelReasoningPathService:
        core_factory = self._require_core_factory()
        projection_factory = self._require_projection_factory()
        return graph_runtime_factories.create_kernel_reasoning_path_service(
            core_factory,
            projection_factory,
            session,
        )

    def create_kernel_claim_projection_readiness_service(
        self,
        session: Session,
    ) -> KernelClaimProjectionReadinessService:
        projection_factory = self._require_projection_factory()
        return graph_runtime_factories.create_kernel_claim_projection_readiness_service(
            projection_factory,
            session,
        )

    def create_kernel_claim_participant_backfill_service(
        self,
        session: Session,
    ) -> KernelClaimParticipantBackfillService:
        core_factory = self._require_core_factory()
        projection_factory = self._require_projection_factory()
        return graph_runtime_factories.create_kernel_claim_participant_backfill_service(
            core_factory,
            projection_factory,
            session,
        )

    def create_hypothesis_generation_service(
        self,
        session: Session,
    ) -> HypothesisGenerationService:
        core_factory = self._require_core_factory()
        projection_factory = self._require_projection_factory()
        return graph_runtime_factories.create_hypothesis_generation_service(
            core_factory,
            projection_factory,
            session,
        )


__all__ = ["KernelReasoningHypothesisServiceFactoryMixin"]
