"""Reasoning, readiness, and hypothesis service factory mixin."""

from __future__ import annotations

from typing import TYPE_CHECKING

import src.infrastructure.repositories.kernel as kernel_repositories
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
from src.domain.agents.models import ModelCapability
from src.infrastructure.llm.config.model_registry import get_model_registry
from src.infrastructure.repositories.source_document_repository import (
    SqlAlchemySourceDocumentRepository,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from src.application.agents.services.hypothesis_generation_service import (
        HypothesisGenerationService,
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
        from src.application.services.kernel._kernel_graph_view_support import (
            KernelGraphViewServiceDependencies,
        )

        return KernelGraphViewService(
            KernelGraphViewServiceDependencies(
                entity_service=core_factory.create_kernel_entity_service(session),  # type: ignore[attr-defined]
                relation_service=core_factory.create_kernel_relation_service(session),  # type: ignore[attr-defined]
                relation_claim_service=projection_factory.create_kernel_relation_claim_service(  # type: ignore[attr-defined]
                    session,
                ),
                claim_participant_service=projection_factory.create_kernel_claim_participant_service(  # type: ignore[attr-defined]
                    session,
                ),
                claim_relation_service=projection_factory.create_kernel_claim_relation_service(  # type: ignore[attr-defined]
                    session,
                ),
                claim_evidence_service=projection_factory.create_kernel_claim_evidence_service(  # type: ignore[attr-defined]
                    session,
                ),
                source_document_repository=SqlAlchemySourceDocumentRepository(session),
            ),
        )

    def create_kernel_reasoning_path_service(
        self,
        session: Session,
    ) -> KernelReasoningPathService:
        core_factory = self._require_core_factory()
        projection_factory = self._require_projection_factory()
        return KernelReasoningPathService(
            reasoning_path_repo=kernel_repositories.SqlAlchemyKernelReasoningPathRepository(
                session,
            ),
            relation_claim_service=projection_factory.create_kernel_relation_claim_service(  # type: ignore[attr-defined]
                session,
            ),
            claim_participant_service=projection_factory.create_kernel_claim_participant_service(  # type: ignore[attr-defined]
                session,
            ),
            claim_evidence_service=projection_factory.create_kernel_claim_evidence_service(session),  # type: ignore[attr-defined]
            claim_relation_service=projection_factory.create_kernel_claim_relation_service(session),  # type: ignore[attr-defined]
            relation_service=core_factory.create_kernel_relation_service(session),  # type: ignore[attr-defined]
            session=session,
        )

    def create_kernel_claim_projection_readiness_service(
        self,
        session: Session,
    ) -> KernelClaimProjectionReadinessService:
        projection_factory = self._require_projection_factory()
        return KernelClaimProjectionReadinessService(
            session=session,
            relation_projection_invariant_service=(
                projection_factory.create_kernel_relation_projection_invariant_service(  # type: ignore[attr-defined]
                    session,
                )
            ),
            relation_projection_materialization_service=(
                projection_factory.create_kernel_relation_projection_materialization_service(  # type: ignore[attr-defined]
                    session,
                )
            ),
            claim_participant_backfill_service=self.create_kernel_claim_participant_backfill_service(
                session,
            ),
        )

    def create_kernel_claim_participant_backfill_service(
        self,
        session: Session,
    ) -> KernelClaimParticipantBackfillService:
        core_factory = self._require_core_factory()
        projection_factory = self._require_projection_factory()
        return KernelClaimParticipantBackfillService(
            session=session,
            relation_claim_service=projection_factory.create_kernel_relation_claim_service(  # type: ignore[attr-defined]
                session,
            ),
            claim_participant_service=projection_factory.create_kernel_claim_participant_service(  # type: ignore[attr-defined]
                session,
            ),
            entity_repository=core_factory._build_entity_repository(session),  # type: ignore[attr-defined]  # noqa: SLF001
            concept_service=core_factory.create_concept_management_service(session),  # type: ignore[attr-defined]
            reasoning_path_service=self.create_kernel_reasoning_path_service(session),
        )

    def create_hypothesis_generation_service(
        self,
        session: Session,
    ) -> HypothesisGenerationService:
        core_factory = self._require_core_factory()
        projection_factory = self._require_projection_factory()
        from src.application.agents.services.hypothesis_generation_service import (
            HypothesisGenerationService,
            HypothesisGenerationServiceDependencies,
        )
        from src.infrastructure.llm.adapters import ArtanaGraphConnectionAdapter

        dictionary_service = core_factory.create_dictionary_management_service(session)  # type: ignore[attr-defined]
        relation_repository = kernel_repositories.SqlAlchemyKernelRelationRepository(
            session,
        )
        graph_query_service = kernel_repositories.SqlAlchemyGraphQueryRepository(
            session,
        )
        model_spec = get_model_registry().get_default_model(
            ModelCapability.EVIDENCE_EXTRACTION,
        )
        graph_connection_agent = ArtanaGraphConnectionAdapter(
            model=model_spec.model_id,
            dictionary_service=dictionary_service,
            graph_query_service=graph_query_service,
            relation_repository=relation_repository,
        )
        return HypothesisGenerationService(
            dependencies=HypothesisGenerationServiceDependencies(
                graph_connection_agent=graph_connection_agent,
                relation_claim_service=projection_factory.create_kernel_relation_claim_service(  # type: ignore[attr-defined]
                    session,
                ),
                claim_participant_service=projection_factory.create_kernel_claim_participant_service(  # type: ignore[attr-defined]
                    session,
                ),
                claim_evidence_service=projection_factory.create_kernel_claim_evidence_service(  # type: ignore[attr-defined]
                    session,
                ),
                entity_repository=core_factory._build_entity_repository(  # type: ignore[attr-defined]  # noqa: SLF001
                    session,
                ),
                relation_repository=relation_repository,
                dictionary_service=dictionary_service,
                reasoning_path_service=self.create_kernel_reasoning_path_service(
                    session,
                ),
            ),
        )


__all__ = ["KernelReasoningHypothesisServiceFactoryMixin"]
