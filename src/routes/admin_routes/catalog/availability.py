"""Availability endpoints for catalog entries."""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from src.application.services.data_source_activation_service import (
    DataSourceActivationService,
)
from src.application.services.ingestion_scheduling_service import (
    IngestionSchedulingService,
)
from src.application.services.source_management_service import (
    SourceManagementService,
    UpdateSourceRequest,
)
from src.database.session import get_session
from src.domain.entities.data_source_activation import PermissionLevel
from src.domain.entities.user_data_source import SourceStatus
from src.infrastructure.repositories.data_discovery_repository_impl import (
    SQLAlchemySourceCatalogRepository,
)
from src.infrastructure.repositories.user_data_source_repository import (
    SqlAlchemyUserDataSourceRepository,
)
from src.models.database.user_data_source import UserDataSourceModel
from src.routes.admin_routes.dependencies import (
    SYSTEM_ACTOR_ID,
    get_activation_service,
    get_catalog_entry,
    get_ingestion_scheduling_service,
)

from .mappers import availability_summary_to_response
from .schemas import (
    ActivationUpdateRequest,
    BulkActivationUpdateRequest,
    DataSourceAvailabilityResponse,
)

router = APIRouter()
logger = logging.getLogger(__name__)


def _deactivate_configured_sources_for_catalog_entry(
    *,
    session: Session,
    catalog_entry_id: str,
    scheduling_service: IngestionSchedulingService,
    research_space_id: UUID | None = None,
) -> int:
    """Deactivate configured sources linked to a catalog entry when availability forbids execution."""
    catalog_repo = SQLAlchemySourceCatalogRepository(session)
    catalog_entry = catalog_repo.find_by_id(catalog_entry_id)
    if catalog_entry is None or catalog_entry.source_template_id is None:
        return 0

    source_repository = SqlAlchemyUserDataSourceRepository(session)
    source_service = SourceManagementService(source_repository, None)

    query = session.query(UserDataSourceModel).filter(
        UserDataSourceModel.template_id == str(catalog_entry.source_template_id),
    )
    if research_space_id is not None:
        query = query.filter(
            UserDataSourceModel.research_space_id == str(research_space_id),
        )

    rows = query.all()
    updated_count = 0

    for row in rows:
        source_id = UUID(str(row.id))
        source = source_service.get_source(source_id, owner_id=None)
        if source is None:
            continue

        if source.ingestion_schedule.backend_job_id:
            try:
                scheduling_service.unschedule_source(source.id)
            except ValueError:
                logger.debug(
                    "Unable to unschedule source %s while applying availability policy",
                    source.id,
                )

        schedule = source.ingestion_schedule
        schedule_update = None
        if (
            schedule.enabled
            or schedule.backend_job_id is not None
            or schedule.next_run_at is not None
        ):
            schedule_update = schedule.model_copy(
                update={
                    "enabled": False,
                    "backend_job_id": None,
                    "next_run_at": None,
                },
            )

        status_update = (
            SourceStatus.INACTIVE if source.status == SourceStatus.ACTIVE else None
        )

        if status_update is None and schedule_update is None:
            continue

        updated = source_service.update_source(
            source.id,
            UpdateSourceRequest(
                status=status_update,
                ingestion_schedule=schedule_update,
            ),
            owner_id=None,
        )
        if updated is not None:
            updated_count += 1

    return updated_count


@router.get(
    "/availability",
    response_model=list[DataSourceAvailabilityResponse],
    summary="List catalog availability summaries",
)
def list_catalog_availability(
    session: Session = Depends(get_session),
    activation_service: DataSourceActivationService = Depends(get_activation_service),
) -> list[DataSourceAvailabilityResponse]:
    """Return availability summaries for all catalog entries."""
    repo = SQLAlchemySourceCatalogRepository(session)
    entries = repo.find_all()
    summaries = activation_service.get_availability_summaries(
        [entry.id for entry in entries],
    )
    return [availability_summary_to_response(summary) for summary in summaries]


@router.get(
    "/{catalog_entry_id}/availability",
    response_model=DataSourceAvailabilityResponse,
    summary="Get catalog entry availability",
)
def get_catalog_entry_availability(
    catalog_entry_id: str,
    activation_service: DataSourceActivationService = Depends(get_activation_service),
    session: Session = Depends(get_session),
) -> DataSourceAvailabilityResponse:
    """Get availability summary for a single entry."""
    get_catalog_entry(session, catalog_entry_id)
    summary = activation_service.get_availability_summary(catalog_entry_id)
    return availability_summary_to_response(summary)


@router.put(
    "/availability/global",
    response_model=list[DataSourceAvailabilityResponse],
    summary="Bulk set global catalog entry availability",
)
def bulk_set_global_catalog_entry_availability(
    request: BulkActivationUpdateRequest,
    session: Session = Depends(get_session),
    activation_service: DataSourceActivationService = Depends(get_activation_service),
    scheduling_service: IngestionSchedulingService = Depends(
        get_ingestion_scheduling_service,
    ),
) -> list[DataSourceAvailabilityResponse]:
    """Apply a global activation state to multiple entries."""
    repo = SQLAlchemySourceCatalogRepository(session)
    if request.catalog_entry_ids:
        target_ids: list[str] = []
        for catalog_entry_id in request.catalog_entry_ids:
            get_catalog_entry(session, catalog_entry_id)
            target_ids.append(catalog_entry_id)
    else:
        target_ids = [entry.id for entry in repo.find_all()]

    if not target_ids:
        return []

    for catalog_entry_id in target_ids:
        activation_service.set_global_activation(
            catalog_entry_id=catalog_entry_id,
            permission_level=request.permission_level,
            updated_by=SYSTEM_ACTOR_ID,
        )
        if request.permission_level != PermissionLevel.AVAILABLE:
            _deactivate_configured_sources_for_catalog_entry(
                session=session,
                catalog_entry_id=catalog_entry_id,
                scheduling_service=scheduling_service,
            )

    summaries = activation_service.get_availability_summaries(target_ids)
    return [availability_summary_to_response(summary) for summary in summaries]


@router.put(
    "/{catalog_entry_id}/availability/global",
    response_model=DataSourceAvailabilityResponse,
    summary="Set global catalog entry availability",
)
def set_global_catalog_entry_availability(
    catalog_entry_id: str,
    request: ActivationUpdateRequest,
    activation_service: DataSourceActivationService = Depends(get_activation_service),
    scheduling_service: IngestionSchedulingService = Depends(
        get_ingestion_scheduling_service,
    ),
    session: Session = Depends(get_session),
) -> DataSourceAvailabilityResponse:
    """Set global availability for a single entry."""
    get_catalog_entry(session, catalog_entry_id)
    activation_service.set_global_activation(
        catalog_entry_id=catalog_entry_id,
        permission_level=request.permission_level,
        updated_by=SYSTEM_ACTOR_ID,
    )
    if request.permission_level != PermissionLevel.AVAILABLE:
        _deactivate_configured_sources_for_catalog_entry(
            session=session,
            catalog_entry_id=catalog_entry_id,
            scheduling_service=scheduling_service,
        )

    summary = activation_service.get_availability_summary(catalog_entry_id)
    return availability_summary_to_response(summary)


@router.delete(
    "/{catalog_entry_id}/availability/global",
    response_model=DataSourceAvailabilityResponse,
    summary="Clear global availability override",
)
def clear_global_catalog_entry_availability(
    catalog_entry_id: str,
    activation_service: DataSourceActivationService = Depends(get_activation_service),
    session: Session = Depends(get_session),
) -> DataSourceAvailabilityResponse:
    """Remove the global availability override for an entry."""
    get_catalog_entry(session, catalog_entry_id)
    activation_service.clear_global_activation(catalog_entry_id)
    summary = activation_service.get_availability_summary(catalog_entry_id)
    return availability_summary_to_response(summary)


@router.put(
    "/{catalog_entry_id}/availability/research-spaces/{space_id}",
    response_model=DataSourceAvailabilityResponse,
    summary="Set project-specific availability",
)
def set_project_catalog_entry_availability(
    catalog_entry_id: str,
    space_id: UUID,
    request: ActivationUpdateRequest,
    activation_service: DataSourceActivationService = Depends(get_activation_service),
    scheduling_service: IngestionSchedulingService = Depends(
        get_ingestion_scheduling_service,
    ),
    session: Session = Depends(get_session),
) -> DataSourceAvailabilityResponse:
    """Set research-space-specific availability."""
    get_catalog_entry(session, catalog_entry_id)
    activation_service.set_project_activation(
        catalog_entry_id=catalog_entry_id,
        research_space_id=space_id,
        permission_level=request.permission_level,
        updated_by=SYSTEM_ACTOR_ID,
    )
    if request.permission_level != PermissionLevel.AVAILABLE:
        _deactivate_configured_sources_for_catalog_entry(
            session=session,
            catalog_entry_id=catalog_entry_id,
            scheduling_service=scheduling_service,
            research_space_id=space_id,
        )

    summary = activation_service.get_availability_summary(catalog_entry_id)
    return availability_summary_to_response(summary)


@router.delete(
    "/{catalog_entry_id}/availability/research-spaces/{space_id}",
    response_model=DataSourceAvailabilityResponse,
    summary="Clear project-specific availability override",
)
def clear_project_catalog_entry_availability(
    catalog_entry_id: str,
    space_id: UUID,
    activation_service: DataSourceActivationService = Depends(get_activation_service),
    session: Session = Depends(get_session),
) -> DataSourceAvailabilityResponse:
    """Remove the research-space override for an entry."""
    get_catalog_entry(session, catalog_entry_id)
    activation_service.clear_project_activation(
        catalog_entry_id=catalog_entry_id,
        research_space_id=space_id,
    )
    summary = activation_service.get_availability_summary(catalog_entry_id)
    return availability_summary_to_response(summary)


__all__ = ["router"]
