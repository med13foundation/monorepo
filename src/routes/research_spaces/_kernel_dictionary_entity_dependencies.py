"""Dictionary and entity dependency builders."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import Depends
from sqlalchemy.orm import Session

from src.database.session import get_session
from src.infrastructure.dependency_injection.dependencies import (
    get_legacy_dependency_container,
)

if TYPE_CHECKING:
    from src.application.services.kernel.kernel_entity_service import (
        KernelEntityService,
    )
    from src.application.services.kernel.kernel_entity_similarity_service import (
        KernelEntitySimilarityService,
    )
    from src.domain.ports import ConceptPort, DictionaryPort
    from src.domain.repositories.kernel.entity_repository import (
        KernelEntityRepository,
    )


def build_entity_repository(session: Session) -> KernelEntityRepository:
    return get_legacy_dependency_container()._build_entity_repository(
        session,
    )  # noqa: SLF001


def get_dictionary_service(
    session: Session = Depends(get_session),
) -> DictionaryPort:
    return get_legacy_dependency_container().create_dictionary_management_service(
        session,
    )


def get_concept_service(
    session: Session = Depends(get_session),
) -> ConceptPort:
    return get_legacy_dependency_container().create_concept_management_service(
        session,
    )


def get_kernel_entity_service(
    session: Session = Depends(get_session),
) -> KernelEntityService:
    return get_legacy_dependency_container().create_kernel_entity_service(
        session,
    )


def get_kernel_entity_similarity_service(
    session: Session = Depends(get_session),
) -> KernelEntitySimilarityService:
    return get_legacy_dependency_container().create_kernel_entity_similarity_service(
        session,
    )


__all__ = [
    "build_entity_repository",
    "get_concept_service",
    "get_dictionary_service",
    "get_kernel_entity_service",
    "get_kernel_entity_similarity_service",
]
