"""Shared dependencies for admin dictionary routes."""

from __future__ import annotations

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from src.application.services.kernel.dictionary_management_service import (
    DictionaryManagementService,
)
from src.domain.entities.user import User, UserRole
from src.domain.ports import DictionaryPort
from src.infrastructure.embeddings import HybridTextEmbeddingProvider
from src.infrastructure.factories.dictionary_search_harness_factory import (
    create_dictionary_search_harness,
)
from src.infrastructure.repositories.kernel.kernel_dictionary_repository import (
    SqlAlchemyDictionaryRepository,
)
from src.routes.admin_routes.dependencies import get_admin_db_session
from src.routes.auth import get_current_active_user


def require_admin_user(
    current_user: User = Depends(get_current_active_user),
) -> User:
    """Ensure the authenticated user is a platform admin."""
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator role required",
        )
    return current_user


def get_dictionary_service(
    session: Session = Depends(get_admin_db_session),
) -> DictionaryPort:
    """Build a DictionaryManagementService backed by a scoped admin DB session."""
    repo = SqlAlchemyDictionaryRepository(session)
    embedding_provider = HybridTextEmbeddingProvider()
    search_harness = create_dictionary_search_harness(
        dictionary_repo=repo,
        embedding_provider=embedding_provider,
    )
    return DictionaryManagementService(
        dictionary_repo=repo,
        dictionary_search_harness=search_harness,
        embedding_provider=embedding_provider,
    )


__all__ = ["get_dictionary_service", "require_admin_user"]
