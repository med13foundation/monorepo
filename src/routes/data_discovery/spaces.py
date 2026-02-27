"""Route handlers for research space interactions."""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from src.application.services.audit_service import AuditTrailService
from src.application.services.data_discovery_service import DataDiscoveryService
from src.application.services.data_discovery_service.requests import (
    AddSourceToSpaceRequest,
)
from src.database.session import get_session
from src.domain.entities.user import User
from src.infrastructure.dependency_injection.dependencies import (
    get_data_discovery_service_dependency,
)
from src.infrastructure.observability.request_context import get_audit_context
from src.routes.auth import get_current_active_user
from src.type_definitions.common import AuditContext

from .dependencies import (
    get_audit_trail_service,
    owner_filter_for_user,
    require_session_for_user,
)
from .schemas import AddToSpaceRequest

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post(
    "/sessions/{session_id}/add-to-space",
    status_code=status.HTTP_201_CREATED,
    summary="Add source to research space",
    description="Add a tested source from the workbench to a research space as a UserDataSource.",
)
async def add_source_to_space(
    session_id: UUID,
    request: AddToSpaceRequest,
    service: DataDiscoveryService = Depends(get_data_discovery_service_dependency),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_session),
    audit_service: AuditTrailService = Depends(get_audit_trail_service),
    audit_context: AuditContext = Depends(get_audit_context),
) -> dict[str, str]:
    """Add a tested source to a research space."""
    try:
        require_session_for_user(session_id, service, current_user)
        owner_filter = owner_filter_for_user(current_user)

        add_request = AddSourceToSpaceRequest(
            session_id=session_id,
            catalog_entry_id=request.catalog_entry_id,
            research_space_id=request.research_space_id,
            source_config=request.source_config,
        )

        data_source_id = await service.add_source_to_space(
            add_request,
            owner_id=owner_filter,
        )
        if not data_source_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Source could not be added. Verify availability is set to "
                    "Available and source configuration is valid."
                ),
            )

        audit_service.record_action(
            db,
            action="data_discovery.session.add_to_space",
            target=("data_discovery_session", str(session_id)),
            actor_id=current_user.id,
            details={
                "catalog_entry_id": request.catalog_entry_id,
                "research_space_id": str(request.research_space_id),
                "data_source_id": str(data_source_id),
            },
            context=audit_context,
            success=True,
        )
        return {
            "data_source_id": str(data_source_id),
            "message": "Source added to space successfully",
        }

    except HTTPException:
        raise
    except Exception as exc:
        logger.exception(
            "Failed to add source to space from session %s",
            session_id,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to add source to research space",
        ) from exc


__all__ = ["router"]
