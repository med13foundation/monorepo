"""Service-local governance adapters for the standalone graph API."""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.application.services.kernel.concept_management_service import (
    ConceptManagementService,
)
from src.application.services.kernel.dictionary_management_service import (
    DictionaryManagementService,
)
from src.infrastructure.embeddings import HybridTextEmbeddingProvider
from src.infrastructure.factories.dictionary_search_harness_factory import (
    create_dictionary_search_harness,
)
from src.infrastructure.graph_governance.concept_repository import (
    GraphConceptRepository,
)
from src.infrastructure.graph_governance.dictionary_repository import (
    GraphDictionaryRepository,
)
from src.infrastructure.llm.adapters.concept_decision_harness_adapter import (
    DeterministicConceptDecisionHarnessAdapter,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from src.domain.ports.concept_port import ConceptPort
    from src.domain.ports.dictionary_port import DictionaryPort
    from src.domain.repositories.kernel.concept_repository import ConceptRepository
    from src.domain.repositories.kernel.dictionary_repository import (
        DictionaryRepository,
    )


def build_dictionary_repository(session: Session) -> DictionaryRepository:
    """Build the graph-service dictionary repository adapter."""
    return GraphDictionaryRepository(session)


def build_concept_repository(session: Session) -> ConceptRepository:
    """Build the graph-service concept repository adapter."""
    return GraphConceptRepository(session)


def build_dictionary_service(
    session: Session,
    *,
    embedding_provider: HybridTextEmbeddingProvider | None = None,
) -> DictionaryPort:
    """Build the graph-service dictionary service from local governance adapters."""
    active_embedding_provider = embedding_provider or HybridTextEmbeddingProvider()
    dictionary_repo = build_dictionary_repository(session)
    search_harness = create_dictionary_search_harness(
        dictionary_repo=dictionary_repo,
        embedding_provider=active_embedding_provider,
    )
    return DictionaryManagementService(
        dictionary_repo=dictionary_repo,
        dictionary_search_harness=search_harness,
        embedding_provider=active_embedding_provider,
    )


def build_concept_service(session: Session) -> ConceptPort:
    """Build the graph-service concept service from local governance adapters."""
    return ConceptManagementService(
        concept_repo=build_concept_repository(session),
        concept_harness=DeterministicConceptDecisionHarnessAdapter(),
    )


__all__ = [
    "GraphConceptRepository",
    "GraphDictionaryRepository",
    "build_concept_repository",
    "build_concept_service",
    "build_dictionary_repository",
    "build_dictionary_service",
]
