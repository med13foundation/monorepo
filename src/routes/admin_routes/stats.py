"""
Administrative statistics endpoints.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from src.application.services.source_management_service import (
    SourceManagementService,
)
from src.domain.entities.user_data_source import SourceStatus

from .dependencies import get_source_service

stats_router = APIRouter()


class SystemStatsResponse(BaseModel):
    """Response model for system statistics."""

    total_data_sources: int
    active_data_sources: int
    total_records: int
    system_health: str
    last_updated: str


class DataSourceStats(BaseModel):
    """Statistics for data sources."""

    total_sources: int
    active_sources: int
    error_sources: int
    sources_by_type: dict[str, int]


@stats_router.get(
    "/stats",
    response_model=SystemStatsResponse,
    summary="Get system statistics",
    description="Retrieve overall system statistics for the admin dashboard.",
)
def get_system_stats(
    service: SourceManagementService = Depends(get_source_service),
) -> SystemStatsResponse:
    """Get system-wide statistics."""
    try:
        stats = service.get_statistics()
        data_sources = service.get_active_sources(0, 1000)
        active_sources = len(
            [ds for ds in data_sources if ds.status == SourceStatus.ACTIVE],
        )
        return SystemStatsResponse(
            total_data_sources=stats.get("total_sources", 0),
            active_data_sources=active_sources,
            total_records=0,
            system_health="healthy",
            last_updated="2024-01-01T00:00:00Z",
        )
    except Exception as e:  # pragma: no cover - defensive guard
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get system stats: {e!s}",
        )


@stats_router.get(
    "/data-sources/stats",
    response_model=DataSourceStats,
    summary="Get data source statistics",
    description="Retrieve statistics about data sources grouped by type and status.",
)
def get_data_source_stats(
    service: SourceManagementService = Depends(get_source_service),
) -> DataSourceStats:
    """Get data source statistics."""
    try:
        stats = service.get_statistics()
        all_sources = service.get_active_sources(0, 1000)
        active_sources = len(
            [ds for ds in all_sources if ds.status == SourceStatus.ACTIVE],
        )
        error_sources = 0
        sources_by_type: dict[str, int] = {}
        for ds in all_sources:
            source_type = ds.source_type.value
            sources_by_type[source_type] = sources_by_type.get(source_type, 0) + 1

        total_sources = stats.get("total_sources", len(all_sources))
        return DataSourceStats(
            total_sources=total_sources,
            active_sources=active_sources,
            error_sources=error_sources,
            sources_by_type=sources_by_type,
        )
    except Exception as e:  # pragma: no cover - defensive guard
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get data source stats: {e!s}",
        )


__all__ = ["stats_router"]
