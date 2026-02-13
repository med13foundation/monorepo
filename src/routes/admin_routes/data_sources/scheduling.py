"""Ingestion scheduling endpoints for admin data sources."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from src.application.services.ingestion_scheduling_service import (
    IngestionSchedulingService,
)
from src.application.services.source_management_service import (
    SourceManagementService,
    UpdateSourceRequest,
)
from src.domain.entities.user_data_source import IngestionSchedule
from src.routes.admin_routes.dependencies import (
    get_ingestion_scheduling_service,
    get_source_service,
)

from .schemas import (
    IngestionRunResponse,
    ScheduleConfigurationRequest,
    ScheduleConfigurationResponse,
    ScheduledJobResponse,
)

router = APIRouter()


@router.put(
    "/{source_id}/schedule",
    response_model=ScheduleConfigurationResponse,
    summary="Configure ingestion scheduling",
    description="Update a data source's ingestion schedule and register it with the scheduler backend.",
)
async def configure_ingestion_schedule(
    source_id: UUID,
    request: ScheduleConfigurationRequest,
    source_service: SourceManagementService = Depends(get_source_service),
    scheduling_service: IngestionSchedulingService = Depends(
        get_ingestion_scheduling_service,
    ),
) -> ScheduleConfigurationResponse:
    """Update ingestion schedule and register/unschedule jobs accordingly."""
    ingestion_schedule = IngestionSchedule(
        enabled=request.enabled,
        frequency=request.frequency,
        start_time=request.start_time,
        timezone=request.timezone,
        cron_expression=request.cron_expression,
    )
    update_request = UpdateSourceRequest(ingestion_schedule=ingestion_schedule)
    updated_source = source_service.update_source(
        source_id,
        update_request,
        owner_id=None,
    )
    if not updated_source:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Data source not found",
        )

    scheduled_job: ScheduledJobResponse | None = None
    try:
        if ingestion_schedule.requires_scheduler:
            scheduled = await scheduling_service.schedule_source(source_id)
            scheduled_job = ScheduledJobResponse(
                job_id=scheduled.job_id,
                source_id=scheduled.source_id,
                next_run_at=scheduled.next_run_at,
                frequency=scheduled.schedule.frequency,
                cron_expression=scheduled.schedule.cron_expression,
            )
        else:
            scheduling_service.unschedule_source(source_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    refreshed_source = source_service.get_source(source_id)
    if refreshed_source is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Data source not found after update",
        )

    return ScheduleConfigurationResponse(
        ingestion_schedule=refreshed_source.ingestion_schedule,
        scheduled_job=scheduled_job,
    )


@router.post(
    "/{source_id}/schedule/run",
    response_model=IngestionRunResponse,
    summary="Trigger an ingestion run",
    description="Manually trigger ingestion for a data source outside its normal schedule.",
)
async def trigger_ingestion_run(
    source_id: UUID,
    scheduling_service: IngestionSchedulingService = Depends(
        get_ingestion_scheduling_service,
    ),
) -> IngestionRunResponse:
    """Execute ingestion immediately for a data source."""
    try:
        summary = await scheduling_service.trigger_ingestion(source_id)
    except ValueError as exc:
        detail = str(exc)
        lowered_detail = detail.lower()
        if "already running" in lowered_detail:
            status_code = status.HTTP_409_CONFLICT
        elif "not found" in lowered_detail:
            status_code = status.HTTP_404_NOT_FOUND
        else:
            status_code = status.HTTP_400_BAD_REQUEST
        raise HTTPException(
            status_code=status_code,
            detail=detail,
        ) from exc
    return IngestionRunResponse(
        source_id=summary.source_id,
        fetched_records=summary.fetched_records,
        parsed_publications=summary.parsed_publications,
        created_publications=summary.created_publications,
        updated_publications=summary.updated_publications,
        executed_query=summary.executed_query,
    )


__all__ = ["router"]
