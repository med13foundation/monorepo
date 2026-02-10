"""Dependencies for kernel (entities/observations/relations/provenance) routes."""

from __future__ import annotations

from fastapi import Depends
from sqlalchemy.orm import Session

from src.application.services.kernel import (
    DictionaryService,
    KernelEntityService,
    KernelObservationService,
    KernelRelationService,
    ProvenanceService,
)
from src.database.session import get_session
from src.infrastructure.factories.ingestion_pipeline_factory import (
    create_ingestion_pipeline,
)
from src.infrastructure.ingestion.pipeline import IngestionPipeline
from src.infrastructure.repositories.kernel import (
    SqlAlchemyDictionaryRepository,
    SqlAlchemyKernelEntityRepository,
    SqlAlchemyKernelObservationRepository,
    SqlAlchemyKernelRelationRepository,
    SqlAlchemyProvenanceRepository,
)


def get_dictionary_service(
    session: Session = Depends(get_session),
) -> DictionaryService:
    """Kernel dictionary service (read/write)."""
    dictionary_repo = SqlAlchemyDictionaryRepository(session)
    return DictionaryService(dictionary_repo=dictionary_repo)


def get_kernel_entity_service(
    session: Session = Depends(get_session),
) -> KernelEntityService:
    """Kernel entity CRUD + resolution service."""
    entity_repo = SqlAlchemyKernelEntityRepository(session)
    dictionary_repo = SqlAlchemyDictionaryRepository(session)
    return KernelEntityService(
        entity_repo=entity_repo,
        dictionary_repo=dictionary_repo,
    )


def get_kernel_observation_service(
    session: Session = Depends(get_session),
) -> KernelObservationService:
    """Kernel observation service (typed fact writes/reads)."""
    observation_repo = SqlAlchemyKernelObservationRepository(session)
    entity_repo = SqlAlchemyKernelEntityRepository(session)
    dictionary_repo = SqlAlchemyDictionaryRepository(session)
    return KernelObservationService(
        observation_repo=observation_repo,
        entity_repo=entity_repo,
        dictionary_repo=dictionary_repo,
    )


def get_kernel_relation_service(
    session: Session = Depends(get_session),
) -> KernelRelationService:
    """Kernel relation service (graph edges + curation lifecycle)."""
    relation_repo = SqlAlchemyKernelRelationRepository(session)
    entity_repo = SqlAlchemyKernelEntityRepository(session)
    dictionary_repo = SqlAlchemyDictionaryRepository(session)
    return KernelRelationService(
        relation_repo=relation_repo,
        entity_repo=entity_repo,
        dictionary_repo=dictionary_repo,
    )


def get_provenance_service(
    session: Session = Depends(get_session),
) -> ProvenanceService:
    """Kernel provenance service."""
    provenance_repo = SqlAlchemyProvenanceRepository(session)
    return ProvenanceService(provenance_repo=provenance_repo)


def get_ingestion_pipeline(
    session: Session = Depends(get_session),
) -> IngestionPipeline:
    """Fully wired ingestion pipeline (map -> normalize -> resolve -> validate)."""
    return create_ingestion_pipeline(session)


__all__ = [
    "get_dictionary_service",
    "get_kernel_entity_service",
    "get_kernel_observation_service",
    "get_kernel_relation_service",
    "get_provenance_service",
    "get_ingestion_pipeline",
]
