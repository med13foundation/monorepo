"""Space-scoped ingestion execution endpoints."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from fastapi import Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.application.services import (
    DataSourceActivationService,
    IngestionSchedulingService,
    MembershipManagementService,
    SourceManagementService,
)
from src.database.session import get_session
from src.domain.entities.data_source_activation import PermissionLevel
from src.domain.entities.user import User
from src.domain.entities.user_data_source import SourceStatus, UserDataSource
from src.infrastructure.repositories.user_data_source_repository import (
    SqlAlchemyUserDataSourceRepository,
)
from src.models.database.data_discovery import SourceCatalogEntryModel
from src.routes.auth import get_current_active_user
from src.routes.research_spaces.dependencies import (
    get_activation_service_for_space,
    get_ingestion_scheduling_service_for_space,
    get_membership_service,
    get_source_service_for_space,
    require_researcher_role,
)

from .kernel_ingestion_schemas import (
    SpaceRunActiveSourcesResponse,
    SpaceSourceIngestionRunResponse,
)
from .router import (
    HTTP_400_BAD_REQUEST,
    HTTP_403_FORBIDDEN,
    HTTP_404_NOT_FOUND,
    HTTP_500_INTERNAL_SERVER_ERROR,
    research_spaces_router,
)


def _resolve_catalog_entry_id_for_source(
    session: Session,
    source: UserDataSource,
) -> str | None:
    if source.template_id is None:
        return None

    statement = (
        select(SourceCatalogEntryModel.id)
        .where(SourceCatalogEntryModel.source_template_id == str(source.template_id))
        .limit(1)
    )
    catalog_entry_id = session.execute(statement).scalar_one_or_none()
    if catalog_entry_id is None:
        return None
    return str(catalog_entry_id)


def _get_source_run_blocker(
    source: UserDataSource,
    space_id: UUID,
    session: Session,
    activation_service: DataSourceActivationService,
) -> tuple[int, str] | None:
    if source.status != SourceStatus.ACTIVE:
        return (
            HTTP_400_BAD_REQUEST,
            "Source must be active before ingestion can run",
        )

    if not source.ingestion_schedule.requires_scheduler:
        return (
            HTTP_400_BAD_REQUEST,
            "Source must have an enabled non-manual ingestion schedule",
        )

    catalog_entry_id = _resolve_catalog_entry_id_for_source(session, source)
    if catalog_entry_id is None:
        return None

    permission_level = activation_service.get_effective_permission_level(
        catalog_entry_id,
        space_id,
    )
    if permission_level != PermissionLevel.AVAILABLE:
        return (
            HTTP_403_FORBIDDEN,
            "Source is not available for ingestion in this space",
        )

    return None


def _summary_to_run_response(
    source_name: str,
    summary_status: Literal["completed", "skipped", "failed"],
    source_id: UUID,
    *,
    message: str | None = None,
    fetched_records: int = 0,
    parsed_publications: int = 0,
    created_publications: int = 0,
    updated_publications: int = 0,
    executed_query: str | None = None,
) -> SpaceSourceIngestionRunResponse:
    return SpaceSourceIngestionRunResponse(
        source_id=source_id,
        source_name=source_name,
        status=summary_status,
        message=message,
        fetched_records=fetched_records,
        parsed_publications=parsed_publications,
        created_publications=created_publications,
        updated_publications=updated_publications,
        executed_query=executed_query,
    )


@research_spaces_router.post(
    "/{space_id}/ingest/sources/{source_id}/run",
    response_model=SpaceSourceIngestionRunResponse,
    summary="Run ingestion for a configured source",
    description=(
        "Trigger ingestion for a single configured source in this research space."
    ),
)
async def run_space_source_ingestion(
    space_id: UUID,
    source_id: UUID,
    *,
    current_user: User = Depends(get_current_active_user),
    membership_service: MembershipManagementService = Depends(get_membership_service),
    source_service: SourceManagementService = Depends(get_source_service_for_space),
    activation_service: DataSourceActivationService = Depends(
        get_activation_service_for_space,
    ),
    scheduling_service: IngestionSchedulingService = Depends(
        get_ingestion_scheduling_service_for_space,
    ),
    session: Session = Depends(get_session),
) -> SpaceSourceIngestionRunResponse:
    require_researcher_role(
        space_id,
        current_user.id,
        membership_service,
        session,
        current_user.role,
    )

    source = source_service.get_source(source_id, owner_id=None)
    if source is None or source.research_space_id != space_id:
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND,
            detail="Data source not found in this research space",
        )

    blocker = _get_source_run_blocker(
        source,
        space_id,
        session,
        activation_service,
    )
    if blocker is not None:
        status_code, detail = blocker
        raise HTTPException(status_code=status_code, detail=detail)

    try:
        summary = await scheduling_service.trigger_ingestion(source.id)
    except ValueError as exc:
        detail = str(exc)
        lowered_detail = detail.lower()
        if "already running" in lowered_detail:
            status_code = 409
        elif "not found" in lowered_detail:
            status_code = HTTP_404_NOT_FOUND
        else:
            status_code = HTTP_400_BAD_REQUEST
        raise HTTPException(
            status_code=status_code,
            detail=detail,
        ) from exc
    except Exception as exc:  # pragma: no cover - defensive guard
        raise HTTPException(
            status_code=HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to run ingestion: {exc!s}",
        ) from exc

    return _summary_to_run_response(
        source_name=source.name,
        summary_status="completed",
        source_id=summary.source_id,
        fetched_records=summary.fetched_records,
        parsed_publications=summary.parsed_publications,
        created_publications=summary.created_publications,
        updated_publications=summary.updated_publications,
        executed_query=summary.executed_query,
    )


@research_spaces_router.post(
    "/{space_id}/ingest/run",
    response_model=SpaceRunActiveSourcesResponse,
    summary="Run ingestion for all active sources in this space",
    description=(
        "Trigger ingestion for all active, runnable data sources in this research "
        "space. Sources that are inactive or unavailable are skipped."
    ),
)
async def run_all_active_space_sources_ingestion(
    space_id: UUID,
    current_user: User = Depends(get_current_active_user),
    membership_service: MembershipManagementService = Depends(get_membership_service),
    activation_service: DataSourceActivationService = Depends(
        get_activation_service_for_space,
    ),
    scheduling_service: IngestionSchedulingService = Depends(
        get_ingestion_scheduling_service_for_space,
    ),
    session: Session = Depends(get_session),
) -> SpaceRunActiveSourcesResponse:
    require_researcher_role(
        space_id,
        current_user.id,
        membership_service,
        session,
        current_user.role,
    )

    source_repository = SqlAlchemyUserDataSourceRepository(session)
    sources = source_repository.find_by_research_space(space_id, skip=0, limit=1000)
    active_sources = [
        source for source in sources if source.status == SourceStatus.ACTIVE
    ]

    runs: list[SpaceSourceIngestionRunResponse] = []
    runnable_sources = 0
    completed_sources = 0
    skipped_sources = 0
    failed_sources = 0

    for source in active_sources:
        blocker = _get_source_run_blocker(
            source,
            space_id,
            session,
            activation_service,
        )
        if blocker is not None:
            _, detail = blocker
            runs.append(
                _summary_to_run_response(
                    source_name=source.name,
                    summary_status="skipped",
                    source_id=source.id,
                    message=detail,
                ),
            )
            skipped_sources += 1
            continue

        runnable_sources += 1

        try:
            summary = await scheduling_service.trigger_ingestion(source.id)
        except ValueError as exc:
            message = str(exc)
            if "already running" in message.lower():
                runs.append(
                    _summary_to_run_response(
                        source_name=source.name,
                        summary_status="skipped",
                        source_id=source.id,
                        message=message,
                    ),
                )
                skipped_sources += 1
                continue
            runs.append(
                _summary_to_run_response(
                    source_name=source.name,
                    summary_status="failed",
                    source_id=source.id,
                    message=message,
                ),
            )
            failed_sources += 1
            continue
        except Exception as exc:  # pragma: no cover - defensive guard
            runs.append(
                _summary_to_run_response(
                    source_name=source.name,
                    summary_status="failed",
                    source_id=source.id,
                    message=str(exc),
                ),
            )
            failed_sources += 1
            continue

        runs.append(
            _summary_to_run_response(
                source_name=source.name,
                summary_status="completed",
                source_id=summary.source_id,
                fetched_records=summary.fetched_records,
                parsed_publications=summary.parsed_publications,
                created_publications=summary.created_publications,
                updated_publications=summary.updated_publications,
                executed_query=summary.executed_query,
            ),
        )
        completed_sources += 1

    return SpaceRunActiveSourcesResponse(
        total_sources=len(sources),
        active_sources=len(active_sources),
        runnable_sources=runnable_sources,
        completed_sources=completed_sources,
        skipped_sources=skipped_sources,
        failed_sources=failed_sources,
        runs=runs,
    )


__all__ = ["run_all_active_space_sources_ingestion", "run_space_source_ingestion"]
