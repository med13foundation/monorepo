"""Route handler for querying the source catalog."""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from src.application.services.data_discovery_service import DataDiscoveryService
from src.infrastructure.dependency_injection.dependencies import (
    get_data_discovery_service_dependency,
)

from .mappers import catalog_entry_to_response
from .schemas import SourceCatalogResponse

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get(
    "/catalog",
    response_model=list[SourceCatalogResponse],
    summary="Get source catalog",
    description="Retrieve the source catalog, optionally filtered by category or search query.",
)
def get_source_catalog(
    category: str | None = Query(None, description="Filter by category"),
    search: str | None = Query(None, description="Search query"),
    research_space_id: UUID | None = Query(
        None,
        description="Optional research space context for availability filtering",
    ),
    service: DataDiscoveryService = Depends(get_data_discovery_service_dependency),
) -> list[SourceCatalogResponse]:
    """Get the source catalog with optional filtering."""
    try:
        entries = service.get_source_catalog(
            category,
            search,
            research_space_id=research_space_id,
        )
        return [catalog_entry_to_response(entry) for entry in entries]

    except Exception as exc:
        logger.exception("Failed to retrieve source catalog")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve source catalog",
        ) from exc


__all__ = ["router"]
