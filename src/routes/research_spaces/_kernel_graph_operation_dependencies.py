"""Graph operation dependency builders."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import Depends
from sqlalchemy.orm import Session

from src.database.session import get_session
from src.infrastructure.dependency_injection.dependencies import (
    get_legacy_dependency_container,
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
    from src.infrastructure.ingestion.pipeline import IngestionPipeline


def get_kernel_observation_service(
    session: Session = Depends(get_session),
) -> KernelObservationService:
    return get_legacy_dependency_container().create_kernel_observation_service(
        session,
    )


def get_kernel_relation_service(
    session: Session = Depends(get_session),
) -> KernelRelationService:
    return get_legacy_dependency_container().create_kernel_relation_service(
        session,
    )


def get_kernel_relation_suggestion_service(
    session: Session = Depends(get_session),
) -> KernelRelationSuggestionService:
    return get_legacy_dependency_container().create_kernel_relation_suggestion_service(
        session,
    )


def get_provenance_service(
    session: Session = Depends(get_session),
) -> ProvenanceService:
    return get_legacy_dependency_container().create_provenance_service(
        session,
    )


def get_ingestion_pipeline(
    session: Session = Depends(get_session),
) -> IngestionPipeline:
    return get_legacy_dependency_container().create_ingestion_pipeline(session)


__all__ = [
    "get_ingestion_pipeline",
    "get_kernel_observation_service",
    "get_kernel_relation_service",
    "get_kernel_relation_suggestion_service",
    "get_provenance_service",
]
