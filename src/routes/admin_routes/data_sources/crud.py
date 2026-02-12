"""CRUD endpoints for admin data source management."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from src.application.services.data_source_authorization_service import (
    DataSourceAuthorizationService,
)
from src.application.services.source_management_service import (
    CreateSourceRequest,
    SourceManagementService,
    UpdateSourceRequest,
)
from src.routes.admin_routes.dependencies import (
    DEFAULT_OWNER_ID,
    get_auth_service,
    get_source_service,
)

from .mappers import data_source_to_response
from .schemas import (
    CreateDataSourceRequest,
    DataSourceResponse,
    UpdateDataSourceRequest,
)

router = APIRouter()


@router.post(
    "",
    response_model=DataSourceResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create data source",
    description="Create a new data source configuration.",
)
async def create_data_source(
    request: CreateDataSourceRequest,
    service: SourceManagementService = Depends(get_source_service),
    auth_service: DataSourceAuthorizationService = Depends(
        get_auth_service,
    ),  # noqa: ARG001
) -> DataSourceResponse:
    """Create a new data source."""
    try:
        create_request = CreateSourceRequest(
            owner_id=DEFAULT_OWNER_ID,
            name=request.name,
            source_type=request.source_type,
            description=request.description or "",
            configuration=request.config.model_copy(),
            template_id=request.template_id,
        )
        data_source = service.create_source(create_request)
        return data_source_to_response(data_source)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover - defensive guard
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create data source: {exc!s}",
        )


@router.get(
    "/{source_id}",
    response_model=DataSourceResponse,
    summary="Get data source",
    description="Retrieve detailed information about a specific data source.",
)
async def get_data_source(
    source_id: UUID,
    service: SourceManagementService = Depends(get_source_service),
) -> DataSourceResponse:
    """Get a specific data source by ID."""
    try:
        data_source = service.get_source(source_id)
        if not data_source:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Data source not found",
            )
        return data_source_to_response(data_source)
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover - defensive guard
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get data source: {exc!s}",
        )


@router.put(
    "/{source_id}",
    response_model=DataSourceResponse,
    summary="Update data source",
    description="Update an existing data source configuration.",
)
async def update_data_source(
    source_id: UUID,
    request: UpdateDataSourceRequest,
    service: SourceManagementService = Depends(get_source_service),
    auth_service: DataSourceAuthorizationService = Depends(
        get_auth_service,
    ),  # noqa: ARG001
) -> DataSourceResponse:
    """Update an existing data source."""
    try:
        update_request = UpdateSourceRequest(
            name=request.name,
            description=request.description,
            status=request.status,
            configuration=(request.config.model_copy() if request.config else None),
            ingestion_schedule=(
                request.ingestion_schedule.model_copy()
                if request.ingestion_schedule
                else None
            ),
        )
        data_source = service.update_source(
            source_id,
            update_request,
            owner_id=None,
        )
        if not data_source:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Data source not found",
            )
        return data_source_to_response(data_source)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover - defensive guard
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update data source: {exc!s}",
        )


@router.delete(
    "/{source_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete data source",
    description="Delete an existing data source.",
)
async def delete_data_source(
    source_id: UUID,
    service: SourceManagementService = Depends(get_source_service),
    auth_service: DataSourceAuthorizationService = Depends(
        get_auth_service,
    ),  # noqa: ARG001
) -> None:
    """Delete a data source."""
    try:
        success = service.delete_source(source_id, owner_id=None)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Data source not found",
            )
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover - defensive guard
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete data source: {exc!s}",
        )


__all__ = ["router"]
