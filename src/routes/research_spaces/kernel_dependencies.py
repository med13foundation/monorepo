"""Dependencies for kernel (entities/observations/relations/provenance) routes."""

from __future__ import annotations

from fastapi import Depends
from sqlalchemy.orm import Session

from src.application.services.kernel import (
    DictionaryManagementService,
    KernelEntityService,
    KernelObservationService,
    KernelRelationService,
    ProvenanceService,
)
from src.database.session import get_session
from src.domain.ports import DictionaryPort
from src.infrastructure.embeddings import HybridTextEmbeddingProvider
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
from src.infrastructure.security.phi_encryption import (
    build_phi_encryption_service_from_env,
    is_phi_encryption_enabled,
)


def _build_entity_repository(session: Session) -> SqlAlchemyKernelEntityRepository:
    enable_phi_encryption = is_phi_encryption_enabled()
    phi_encryption_service = (
        build_phi_encryption_service_from_env() if enable_phi_encryption else None
    )
    return SqlAlchemyKernelEntityRepository(
        session,
        phi_encryption_service=phi_encryption_service,
        enable_phi_encryption=enable_phi_encryption,
    )


def get_dictionary_service(
    session: Session = Depends(get_session),
) -> DictionaryPort:
    """Kernel dictionary service (read/write)."""
    dictionary_repo = SqlAlchemyDictionaryRepository(session)
    return DictionaryManagementService(
        dictionary_repo=dictionary_repo,
        embedding_provider=HybridTextEmbeddingProvider(),
    )


def get_kernel_entity_service(
    session: Session = Depends(get_session),
) -> KernelEntityService:
    """Kernel entity CRUD + resolution service."""
    entity_repo = _build_entity_repository(session)
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
    entity_repo = _build_entity_repository(session)
    dictionary_repo = SqlAlchemyDictionaryRepository(session)
    dictionary_service = DictionaryManagementService(
        dictionary_repo=dictionary_repo,
        embedding_provider=HybridTextEmbeddingProvider(),
    )
    return KernelObservationService(
        observation_repo=observation_repo,
        entity_repo=entity_repo,
        dictionary_repo=dictionary_service,
    )


def get_kernel_relation_service(
    session: Session = Depends(get_session),
) -> KernelRelationService:
    """Kernel relation service (graph edges + curation lifecycle)."""
    relation_repo = SqlAlchemyKernelRelationRepository(session)
    entity_repo = _build_entity_repository(session)
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
