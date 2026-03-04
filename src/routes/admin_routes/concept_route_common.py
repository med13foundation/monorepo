"""Shared dependencies for Concept Manager admin routes."""

from __future__ import annotations

from fastapi import Depends
from sqlalchemy.orm import Session

from src.application.services.kernel.concept_management_service import (
    ConceptManagementService,
)
from src.domain.ports.concept_port import ConceptPort
from src.infrastructure.llm.adapters.concept_decision_harness_adapter import (
    DeterministicConceptDecisionHarnessAdapter,
)
from src.infrastructure.repositories.kernel.kernel_concept_repository import (
    SqlAlchemyConceptRepository,
)
from src.routes.admin_routes.dependencies import get_admin_db_session

from .dictionary_route_common import require_admin_user


def get_concept_service(
    session: Session = Depends(get_admin_db_session),
) -> ConceptPort:
    """Build a ConceptManagementService for admin-scoped sessions."""
    repo = SqlAlchemyConceptRepository(session)
    harness = DeterministicConceptDecisionHarnessAdapter()
    return ConceptManagementService(
        concept_repo=repo,
        concept_harness=harness,
    )


__all__ = ["get_concept_service", "require_admin_user"]
