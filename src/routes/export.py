"""
Bulk Export API routes for MED13 Resource Library.

Provides streaming data export capabilities in multiple formats.
"""

import gzip
from collections.abc import Generator
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from src.application.export.export_service import BulkExportService
from src.application.export.export_types import CompressionFormat, ExportFormat
from src.application.services.membership_management_service import (
    MembershipManagementService,
)
from src.database.session import get_session
from src.domain.entities.user import User
from src.infrastructure.dependency_injection.dependencies import (
    get_legacy_dependency_container,
)
from src.models.api.common import (
    ExportableEntitiesResponse,
    ExportEntityInfo,
    ExportOptionsResponse,
    UsageInfo,
)
from src.routes.auth import get_current_active_user
from src.routes.research_spaces.dependencies import (
    get_membership_service,
    verify_space_membership,
)
from src.type_definitions.common import QueryFilters

router = APIRouter(prefix="/export", tags=["export"])


def get_export_service(db: Session = Depends(get_session)) -> BulkExportService:
    """Dependency injection for bulk export service."""
    # Get unified container with legacy support

    container = get_legacy_dependency_container()
    return container.create_export_service(db)


@router.get("/{entity_type}")
def export_entity_data(
    entity_type: str,
    space_id: UUID = Query(..., description="Research space scope"),
    *,
    export_format: ExportFormat = Query(
        ExportFormat.JSON,
        description="Export format",
        alias="format",
    ),
    compression: CompressionFormat = Query(
        CompressionFormat.NONE,
        description="Compression format",
    ),
    limit: int | None = Query(
        None,
        ge=1,
        le=100000,
        description="Maximum number of records to export",
    ),
    kernel_entity_type: str | None = Query(
        None,
        alias="type",
        description="Filter kernel entity_type when exporting entities (e.g. GENE)",
    ),
    current_user: User = Depends(get_current_active_user),
    membership_service: MembershipManagementService = Depends(get_membership_service),
    session: Session = Depends(get_session),
    service: "BulkExportService" = Depends(get_export_service),
) -> StreamingResponse:
    """
    Export data for a specific entity type in the requested format.

    Supports streaming for large datasets to avoid memory issues.
    """
    # Validate entity type
    valid_entity_types = ["entities", "observations", "relations"]
    if entity_type not in valid_entity_types:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid entity type. Supported types: {', '.join(valid_entity_types)}",
        )

    try:
        verify_space_membership(
            space_id,
            current_user.id,
            membership_service,
            session,
            current_user.role,
        )

        filters: QueryFilters = {}
        if limit is not None:
            filters["limit"] = limit
        if entity_type == "entities" and kernel_entity_type is not None:
            filters["entity_type"] = kernel_entity_type

        # Set up filename and content type based on format and compression
        filename = f"{entity_type}.{export_format.value}"
        if compression == CompressionFormat.GZIP:
            filename += ".gz"
            media_type = "application/gzip"
        elif export_format == ExportFormat.JSON:
            media_type = "application/json"
        elif export_format in (ExportFormat.CSV, ExportFormat.TSV):
            media_type = "text/csv"
        elif export_format == ExportFormat.JSONL:
            media_type = "application/x-ndjson"
        else:
            media_type = "application/octet-stream"

        # Create streaming response
        def generate() -> Generator[str | bytes]:
            try:
                yield from service.export_data(
                    research_space_id=str(space_id),
                    entity_type=entity_type,
                    export_format=export_format,
                    compression=compression,
                    filters=filters or None,
                )
            except Exception as e:
                # Log the error and yield an error message
                error_msg = f"Error during export: {e!s}"
                if compression == CompressionFormat.GZIP:
                    yield gzip.compress(error_msg.encode("utf-8"))
                else:
                    yield error_msg

        return StreamingResponse(
            generate(),
            media_type=media_type,
            headers={
                "Content-Disposition": f"attachment; filename={filename}",
                "X-Entity-Type": entity_type,
                "X-Export-Format": export_format.value,
                "X-Compression": compression.value,
            },
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Export failed: {e!s}")


@router.get("/{entity_type}/info", response_model=ExportOptionsResponse)
def get_export_info(
    entity_type: str,
    space_id: UUID = Query(..., description="Research space scope"),
    kernel_entity_type: str | None = Query(
        None,
        alias="type",
        description="Filter kernel entity_type when exporting entities (e.g. GENE)",
    ),
    current_user: User = Depends(get_current_active_user),
    membership_service: MembershipManagementService = Depends(get_membership_service),
    session: Session = Depends(get_session),
    service: "BulkExportService" = Depends(get_export_service),
) -> ExportOptionsResponse:
    """
    Get information about export options and data statistics for an entity type.
    """
    valid_entity_types = ["entities", "observations", "relations"]
    if entity_type not in valid_entity_types:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid entity type. Supported types: {', '.join(valid_entity_types)}",
        )

    try:
        verify_space_membership(
            space_id,
            current_user.id,
            membership_service,
            session,
            current_user.role,
        )

        filters: QueryFilters = {}
        if kernel_entity_type is not None:
            filters["entity_type"] = kernel_entity_type

        info = service.get_export_info(
            research_space_id=str(space_id),
            entity_type=entity_type,
            filters=filters or None,
        )
        return ExportOptionsResponse(
            entity_type=entity_type,
            export_formats=[fmt.value for fmt in ExportFormat],
            compression_formats=[comp.value for comp in CompressionFormat],
            info=info,
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get export info: {e!s}",
        )


@router.get("/", response_model=ExportableEntitiesResponse)
def list_exportable_entities() -> ExportableEntitiesResponse:
    """
    List all entity types that can be exported.
    """
    return ExportableEntitiesResponse(
        exportable_entities=[
            ExportEntityInfo(
                type="entities",
                description="Kernel entities (graph nodes) scoped to a research space",
            ),
            ExportEntityInfo(
                type="observations",
                description="Kernel observations (typed facts) scoped to a research space",
            ),
            ExportEntityInfo(
                type="relations",
                description="Kernel relations (graph edges) scoped to a research space",
            ),
        ],
        supported_formats=[fmt.value for fmt in ExportFormat],
        supported_compression=[comp.value for comp in CompressionFormat],
        usage=UsageInfo(
            endpoint="GET /export/{entity_type}?space_id={uuid}&format=json&compression=gzip",
            description="Download research-space-scoped kernel data in the specified format",
        ),
    )
