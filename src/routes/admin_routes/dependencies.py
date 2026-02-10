"""
Shared dependencies and constants for admin routes.
"""

from __future__ import annotations

from collections.abc import Generator
from uuid import UUID

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from src.application.services import (
    DataSourceActivationService,
    DataSourceAiTestService,
    DataSourceAuthorizationService,
    IngestionSchedulingService,
    SourceManagementService,
    StorageConfigurationService,
    SystemStatusService,
    TemplateManagementService,
)
from src.database import session as session_module
from src.domain.entities.data_discovery_session import SourceCatalogEntry
from src.infrastructure.dependency_injection.container import container
from src.infrastructure.repositories import (
    SqlAlchemyDataSourceActivationRepository,
    SqlAlchemyIngestionJobRepository,
    SQLAlchemySourceCatalogRepository,
    SqlAlchemySourceTemplateRepository,
    SqlAlchemyUserDataSourceRepository,
)

DEFAULT_OWNER_ID = UUID("00000000-0000-0000-0000-000000000001")
SYSTEM_ACTOR_ID = DEFAULT_OWNER_ID


def get_db_session() -> Session:
    """Create a bare SQLAlchemy session for admin services."""
    return session_module.SessionLocal()


def get_admin_db_session() -> Generator[Session]:
    """Yield a scoped SQLAlchemy session for admin endpoints."""

    session = get_db_session()
    try:
        yield session
    finally:
        session.close()


def get_system_status_service() -> SystemStatusService:
    """Return the singleton system status service."""
    return container.get_system_status_service()


def get_source_service(
    session: Session = Depends(get_admin_db_session),
) -> SourceManagementService:
    """Instantiate the SourceManagementService with SQLAlchemy repositories."""
    user_repo = SqlAlchemyUserDataSourceRepository(session)
    template_repo = SqlAlchemySourceTemplateRepository(session)
    return SourceManagementService(user_repo, template_repo)


def get_template_service(
    session: Session = Depends(get_admin_db_session),
) -> TemplateManagementService:
    """Instantiate the TemplateManagementService."""
    template_repo = SqlAlchemySourceTemplateRepository(session)
    return TemplateManagementService(template_repo)


def get_activation_service(
    session: Session = Depends(get_admin_db_session),
) -> DataSourceActivationService:
    """Instantiate the DataSourceActivationService."""
    activation_repo = SqlAlchemyDataSourceActivationRepository(session)
    return DataSourceActivationService(activation_repo)


async def get_auth_service() -> DataSourceAuthorizationService:
    """Instantiate the authorization service."""
    return DataSourceAuthorizationService()


def get_ingestion_scheduling_service() -> Generator[IngestionSchedulingService]:
    """Yield an ingestion scheduling service tied to a scoped session."""
    from src.infrastructure.factories.ingestion_scheduler_factory import (  # noqa: PLC0415
        ingestion_scheduling_service_context,
    )

    with ingestion_scheduling_service_context() as service:
        yield service


def get_data_source_ai_test_service() -> Generator[DataSourceAiTestService]:
    """Yield a data source AI test service tied to a scoped session."""
    from src.infrastructure.factories.data_source_ai_test_factory import (  # noqa: PLC0415
        data_source_ai_test_service_context,
    )

    with data_source_ai_test_service_context() as service:
        yield service


def get_ingestion_job_repository(
    session: Session = Depends(get_admin_db_session),
) -> SqlAlchemyIngestionJobRepository:
    """Instantiate the ingestion job repository."""
    return SqlAlchemyIngestionJobRepository(session)


def get_catalog_entry(session: Session, catalog_entry_id: str) -> SourceCatalogEntry:
    """
    Retrieve a catalog entry or raise HTTP 404.

    Args:
        session: Active database session.
        catalog_entry_id: Identifier of the catalog entry to retrieve.
    """
    repo = SQLAlchemySourceCatalogRepository(session)
    entry = repo.find_by_id(catalog_entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Catalog entry not found")
    return entry


def get_storage_configuration_service(
    session: Session = Depends(get_admin_db_session),
) -> StorageConfigurationService:
    """Instantiate the storage configuration service scoped to the request session."""

    return container.create_storage_configuration_service(session)


__all__ = [
    "DEFAULT_OWNER_ID",
    "SYSTEM_ACTOR_ID",
    "get_activation_service",
    "get_auth_service",
    "get_catalog_entry",
    "get_db_session",
    "get_ingestion_scheduling_service",
    "get_ingestion_job_repository",
    "get_data_source_ai_test_service",
    "get_source_service",
    "get_storage_configuration_service",
    "get_admin_db_session",
    "get_system_status_service",
    "get_template_service",
]
