"""Service-local composition helpers for the standalone graph API."""

from __future__ import annotations

from sqlalchemy.orm import Session

from src.application.services.kernel.kernel_observation_service import (
    KernelObservationService,
)
from src.domain.repositories.kernel.entity_repository import KernelEntityRepository
from src.graph.runtime import create_graph_domain_pack
from src.infrastructure.dependency_injection.graph_runtime_factories import (
    build_relation_repository,
)
from src.infrastructure.repositories.kernel.kernel_entity_repository import (
    SqlAlchemyKernelEntityRepository,
)
from src.infrastructure.repositories.kernel.kernel_observation_repository import (
    SqlAlchemyKernelObservationRepository,
)
from src.infrastructure.security.phi_encryption import (
    build_phi_encryption_service_from_env,
    is_phi_encryption_enabled,
)

from .governance import (
    build_concept_service,
    build_dictionary_repository,
    build_dictionary_service,
)


def build_entity_repository(session: Session) -> KernelEntityRepository:
    """Build the graph-service entity repository with local security wiring."""
    enable_phi_encryption = is_phi_encryption_enabled()
    phi_encryption_service = (
        build_phi_encryption_service_from_env() if enable_phi_encryption else None
    )
    return SqlAlchemyKernelEntityRepository(
        session,
        phi_encryption_service=phi_encryption_service,
        enable_phi_encryption=enable_phi_encryption,
    )


def build_observation_service(
    session: Session,
) -> KernelObservationService:
    """Build the graph-service observation service."""
    graph_domain_pack = create_graph_domain_pack()
    return KernelObservationService(
        observation_repo=SqlAlchemyKernelObservationRepository(
            session,
        ),
        entity_repo=build_entity_repository(session),
        dictionary_repo=build_dictionary_service(
            session,
            dictionary_loading_extension=graph_domain_pack.dictionary_loading_extension,
        ),
    )


__all__ = [
    "build_concept_service",
    "build_dictionary_repository",
    "build_dictionary_service",
    "build_entity_repository",
    "build_observation_service",
    "build_relation_repository",
]
