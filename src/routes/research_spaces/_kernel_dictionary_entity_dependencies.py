"""Dictionary and entity dependency builders."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import Depends
from sqlalchemy.orm import Session

import src.infrastructure.repositories.kernel as kernel_repositories
from src.application.services.kernel.kernel_entity_service import KernelEntityService
from src.database.session import get_session
from src.infrastructure.factories.dictionary_search_harness_factory import (
    create_dictionary_search_harness,
)
from src.infrastructure.security.phi_encryption import (
    build_phi_encryption_service_from_env,
    is_phi_encryption_enabled,
)

if TYPE_CHECKING:
    from src.application.services.kernel.kernel_entity_similarity_service import (
        KernelEntitySimilarityService,
    )
    from src.domain.ports import ConceptPort, DictionaryPort
    from src.domain.repositories.kernel.entity_repository import (
        KernelEntityRepository,
    )


def build_entity_repository(session: Session) -> KernelEntityRepository:
    enable_phi_encryption = is_phi_encryption_enabled()
    phi_encryption_service = (
        build_phi_encryption_service_from_env() if enable_phi_encryption else None
    )
    return kernel_repositories.SqlAlchemyKernelEntityRepository(
        session,
        phi_encryption_service=phi_encryption_service,
        enable_phi_encryption=enable_phi_encryption,
    )


def get_dictionary_service(
    session: Session = Depends(get_session),
) -> DictionaryPort:
    from src.application.services.kernel.dictionary_management_service import (
        DictionaryManagementService,
    )
    from src.infrastructure.embeddings import HybridTextEmbeddingProvider

    dictionary_repo = kernel_repositories.SqlAlchemyDictionaryRepository(session)
    embedding_provider = HybridTextEmbeddingProvider()
    search_harness = create_dictionary_search_harness(
        dictionary_repo=dictionary_repo,
        embedding_provider=embedding_provider,
    )
    return DictionaryManagementService(
        dictionary_repo=dictionary_repo,
        dictionary_search_harness=search_harness,
        embedding_provider=embedding_provider,
    )


def get_concept_service(
    session: Session = Depends(get_session),
) -> ConceptPort:
    from src.application.services.kernel.concept_management_service import (
        ConceptManagementService,
    )
    from src.infrastructure.llm.adapters.concept_decision_harness_adapter import (
        DeterministicConceptDecisionHarnessAdapter,
    )

    return ConceptManagementService(
        concept_repo=kernel_repositories.SqlAlchemyConceptRepository(session),
        concept_harness=DeterministicConceptDecisionHarnessAdapter(),
    )


def get_kernel_entity_service(
    session: Session = Depends(get_session),
) -> KernelEntityService:
    return KernelEntityService(
        entity_repo=build_entity_repository(session),
        dictionary_repo=kernel_repositories.SqlAlchemyDictionaryRepository(session),
    )


def get_kernel_entity_similarity_service(
    session: Session = Depends(get_session),
) -> KernelEntitySimilarityService:
    from src.application.services.kernel.kernel_entity_similarity_service import (
        KernelEntitySimilarityService,
    )
    from src.infrastructure.embeddings import HybridTextEmbeddingProvider

    return KernelEntitySimilarityService(
        entity_repo=build_entity_repository(session),
        embedding_repo=kernel_repositories.SqlAlchemyEntityEmbeddingRepository(session),
        embedding_provider=HybridTextEmbeddingProvider(),
    )


__all__ = [
    "build_entity_repository",
    "get_concept_service",
    "get_dictionary_service",
    "get_kernel_entity_service",
    "get_kernel_entity_similarity_service",
]
