"""Graph operation dependency builders."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import Depends
from sqlalchemy.orm import Session

import src.infrastructure.repositories.kernel as kernel_repositories
from src.database.session import get_session
from src.infrastructure.factories.dictionary_search_harness_factory import (
    create_dictionary_search_harness,
)
from src.infrastructure.factories.ingestion_pipeline_factory import (
    create_ingestion_pipeline,
)
from src.infrastructure.ingestion.pipeline import IngestionPipeline
from src.routes.research_spaces._kernel_dictionary_entity_dependencies import (
    build_entity_repository,
)

if TYPE_CHECKING:
    from src.application.services.kernel.kernel_observation_service import (
        KernelObservationService,
    )
    from src.application.services.kernel.kernel_relation_service import (
        KernelRelationService,
    )
    from src.application.services.kernel.kernel_relation_suggestion_service import (
        KernelRelationSuggestionService,
    )
    from src.application.services.kernel.provenance_service import ProvenanceService


def get_kernel_observation_service(
    session: Session = Depends(get_session),
) -> KernelObservationService:
    from src.application.services.kernel.dictionary_management_service import (
        DictionaryManagementService,
    )
    from src.application.services.kernel.kernel_observation_service import (
        KernelObservationService,
    )
    from src.infrastructure.embeddings import HybridTextEmbeddingProvider

    dictionary_repo = kernel_repositories.SqlAlchemyDictionaryRepository(session)
    embedding_provider = HybridTextEmbeddingProvider()
    search_harness = create_dictionary_search_harness(
        dictionary_repo=dictionary_repo,
        embedding_provider=embedding_provider,
    )
    return KernelObservationService(
        observation_repo=kernel_repositories.SqlAlchemyKernelObservationRepository(
            session,
        ),
        entity_repo=build_entity_repository(session),
        dictionary_repo=DictionaryManagementService(
            dictionary_repo=dictionary_repo,
            dictionary_search_harness=search_harness,
            embedding_provider=embedding_provider,
        ),
    )


def get_kernel_relation_service(
    session: Session = Depends(get_session),
) -> KernelRelationService:
    from src.application.services.kernel.kernel_relation_service import (
        KernelRelationService,
    )

    return KernelRelationService(
        relation_repo=kernel_repositories.SqlAlchemyKernelRelationRepository(session),
        entity_repo=build_entity_repository(session),
    )


def get_kernel_relation_suggestion_service(
    session: Session = Depends(get_session),
) -> KernelRelationSuggestionService:
    from src.application.services.kernel.kernel_relation_suggestion_service import (
        KernelRelationSuggestionService,
    )

    return KernelRelationSuggestionService(
        entity_repo=build_entity_repository(session),
        relation_repo=kernel_repositories.SqlAlchemyKernelRelationRepository(session),
        dictionary_repo=kernel_repositories.SqlAlchemyDictionaryRepository(session),
        embedding_repo=kernel_repositories.SqlAlchemyEntityEmbeddingRepository(session),
    )


def get_provenance_service(
    session: Session = Depends(get_session),
) -> ProvenanceService:
    from src.application.services.kernel.provenance_service import ProvenanceService

    return ProvenanceService(
        provenance_repo=kernel_repositories.SqlAlchemyProvenanceRepository(session),
    )


def get_ingestion_pipeline(
    session: Session = Depends(get_session),
) -> IngestionPipeline:
    return create_ingestion_pipeline(session)


__all__ = [
    "get_ingestion_pipeline",
    "get_kernel_observation_service",
    "get_kernel_relation_service",
    "get_kernel_relation_suggestion_service",
    "get_provenance_service",
]
