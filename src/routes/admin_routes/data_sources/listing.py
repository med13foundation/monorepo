"""Endpoint for listing data sources in the admin API."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from src.application.services.source_management_service import (
    SourceManagementService,
)
from src.database.session import get_session
from src.domain.entities.user_data_source import SourceStatus, SourceType
from src.infrastructure.repositories.user_data_source_repository import (
    SqlAlchemyUserDataSourceRepository,
)
from src.models.api.common import PaginatedResponse
from src.routes.admin_routes.dependencies import get_source_service

from .mappers import data_source_to_response
from .schemas import DataSourceListResponse

router = APIRouter()


@router.get(
    "",
    response_model=DataSourceListResponse,
    summary="List data sources",
    description="Retrieve a paginated list of all data sources with optional filtering.",
)
def list_data_sources(
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    status: SourceStatus | None = Query(None, description="Filter by status"),
    source_type: str | None = Query(None, description="Filter by source type"),
    research_space_id: UUID | None = Query(
        None,
        description="Filter by research space ID",
    ),
    service: SourceManagementService = Depends(get_source_service),
    session: Session = Depends(get_session),
) -> DataSourceListResponse:
    """List data sources with pagination and filtering."""
    try:
        source_repo = SqlAlchemyUserDataSourceRepository(session)

        if research_space_id:
            skip = (page - 1) * limit
            data_sources = source_repo.find_by_research_space(
                research_space_id,
                skip=skip,
                limit=limit,
            )
            total = source_repo.count_by_research_space(research_space_id)
        else:
            all_sources = service.get_active_sources(0, 1000)
            data_sources = all_sources
            if status:
                data_sources = [ds for ds in data_sources if ds.status == status]
            if source_type:
                type_enum = SourceType(source_type)
                data_sources = [
                    ds for ds in data_sources if ds.source_type == type_enum
                ]

            total = len(data_sources)
            start_idx = (page - 1) * limit
            end_idx = start_idx + limit
            data_sources = data_sources[start_idx:end_idx]

        return PaginatedResponse(
            items=[data_source_to_response(ds) for ds in data_sources],
            total=total,
            page=page,
            per_page=limit,
            total_pages=(total + limit - 1) // limit,
            has_next=(page * limit) < total,
            has_prev=page > 1,
        )
    except Exception as exc:  # pragma: no cover - defensive guard
        raise HTTPException(
            status_code=500,
            detail=f"Failed to list data sources: {exc!s}",
        )


__all__ = ["router"]
