# mypy: disable-error-code=no-untyped-def
"""Core kernel service factory mixin."""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.infrastructure.dependency_injection import graph_runtime_factories

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

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
    from src.infrastructure.embeddings import HybridTextEmbeddingProvider


class KernelCoreServiceFactoryMixin:
    """Factory methods for core dictionary, entity, relation, and provenance services."""

    @staticmethod
    def build_dictionary_repository(session: Session):
        return graph_runtime_factories.build_dictionary_repository(session)

    @staticmethod
    def _build_dictionary_repository(session: Session):
        return graph_runtime_factories.build_dictionary_repository(session)

    @staticmethod
    def _build_concept_repository(session: Session):
        return graph_runtime_factories.build_concept_repository(session)

    @staticmethod
    def build_provenance_repository(session: Session):
        return graph_runtime_factories.build_provenance_repository(session)

    @staticmethod
    def _build_provenance_repository(session: Session):
        return graph_runtime_factories.build_provenance_repository(session)

    @staticmethod
    def _build_graph_query_repository(session: Session):
        return graph_runtime_factories.build_graph_query_repository(session)

    @staticmethod
    def _build_entity_repository(session: Session) -> KernelEntityRepository:
        return graph_runtime_factories.build_entity_repository(session)

    def create_kernel_entity_service(
        self,
        session: Session,
    ):
        return graph_runtime_factories.create_kernel_entity_service(session)

    @staticmethod
    def _build_entity_embedding_repository(
        session: Session,
    ) -> EntityEmbeddingRepository:
        return graph_runtime_factories.build_entity_embedding_repository(session)

    @staticmethod
    def _build_observation_repository(
        session: Session,
    ) -> KernelObservationRepository:
        return graph_runtime_factories.build_observation_repository(session)

    @staticmethod
    def _build_relation_repository(
        session: Session,
    ) -> KernelRelationRepository:
        return graph_runtime_factories.build_relation_repository(session)

    @staticmethod
    def _build_relation_claim_repository(
        session: Session,
    ):
        return graph_runtime_factories.build_relation_claim_repository(session)

    @staticmethod
    def _build_relation_projection_source_repository(
        session: Session,
    ):
        return graph_runtime_factories.build_relation_projection_source_repository(
            session,
        )

    @staticmethod
    def _build_claim_participant_repository(
        session: Session,
    ):
        return graph_runtime_factories.build_claim_participant_repository(session)

    @staticmethod
    def _build_claim_evidence_repository(
        session: Session,
    ):
        return graph_runtime_factories.build_claim_evidence_repository(session)

    @staticmethod
    def _build_claim_relation_repository(
        session: Session,
    ):
        return graph_runtime_factories.build_claim_relation_repository(session)

    @staticmethod
    def _build_reasoning_path_repository(
        session: Session,
    ):
        return graph_runtime_factories.build_reasoning_path_repository(session)

    @staticmethod
    def _build_space_registry_repository(
        session: Session,
    ):
        return graph_runtime_factories.build_space_registry_repository(session)

    @staticmethod
    def _build_source_document_reference_repository(
        session: Session,
    ):
        return graph_runtime_factories.build_source_document_reference_repository(
            session,
        )

    def _build_dictionary_service(
        self,
        session: Session,
        *,
        dictionary_search_harness: DictionarySearchHarnessPort | None = None,
        embedding_provider: HybridTextEmbeddingProvider | None = None,
    ) -> DictionaryPort:
        return graph_runtime_factories.build_dictionary_service(
            session,
            dictionary_search_harness=dictionary_search_harness,
            embedding_provider=embedding_provider,
        )

    def build_dictionary_service(
        self,
        session: Session,
        *,
        dictionary_search_harness: DictionarySearchHarnessPort | None = None,
        embedding_provider: HybridTextEmbeddingProvider | None = None,
    ) -> DictionaryPort:
        return graph_runtime_factories.build_dictionary_service(
            session,
            dictionary_search_harness=dictionary_search_harness,
            embedding_provider=embedding_provider,
        )

    @staticmethod
    def build_entity_repository(session: Session) -> KernelEntityRepository:
        return graph_runtime_factories.build_entity_repository(session)

    def create_kernel_entity_similarity_service(
        self,
        session: Session,
    ):
        return graph_runtime_factories.create_kernel_entity_similarity_service(
            session,
        )

    def create_kernel_observation_service(
        self,
        session: Session,
        *,
        dictionary_service: DictionaryPort | None = None,
        entity_repository: KernelEntityRepository | None = None,
        observation_repository: KernelObservationRepository | None = None,
    ):
        return graph_runtime_factories.create_kernel_observation_service(
            session,
            dictionary_service=dictionary_service,
            entity_repository=entity_repository,
            observation_repository=observation_repository,
        )

    def create_kernel_relation_service(
        self,
        session: Session,
    ):
        return graph_runtime_factories.create_kernel_relation_service(session)

    def create_kernel_relation_suggestion_service(
        self,
        session: Session,
    ):
        return graph_runtime_factories.create_kernel_relation_suggestion_service(
            session,
        )

    def create_dictionary_management_service(
        self,
        session: Session,
    ) -> DictionaryPort:
        return graph_runtime_factories.create_dictionary_management_service(
            session,
        )

    def create_concept_management_service(
        self,
        session: Session,
    ) -> ConceptPort:
        return graph_runtime_factories.create_concept_management_service(session)

    def create_provenance_service(
        self,
        session: Session,
    ):
        return graph_runtime_factories.create_provenance_service(session)


__all__ = ["KernelCoreServiceFactoryMixin"]
