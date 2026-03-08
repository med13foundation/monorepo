"""
Admin routes for maintenance mode management.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from src.application.services.system_status_service import SystemStatusService
from src.domain.entities.user import User, UserRole
from src.routes.admin_routes.dependencies import get_system_status_service
from src.routes.auth import get_current_active_user
from src.type_definitions.system_status import (
    EnableMaintenanceRequest,
    MaintenanceModeResponse,
)

router = APIRouter(prefix="/system", tags=["system"])


def require_admin_user(
    current_user: User = Depends(get_current_active_user),
) -> User:
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator role required",
        )
    return current_user


@router.get(
    "/maintenance",
    response_model=MaintenanceModeResponse,
    summary="Get maintenance mode state",
)
async def get_maintenance_state(
    service: SystemStatusService = Depends(get_system_status_service),
) -> MaintenanceModeResponse:
    state = await service.get_maintenance_state()
    return MaintenanceModeResponse(state=state)


@router.post(
    "/maintenance/enable",
    response_model=MaintenanceModeResponse,
    summary="Enable maintenance mode",
)
async def enable_maintenance_mode(
    request: EnableMaintenanceRequest,
    current_user: User = Depends(require_admin_user),
    service: SystemStatusService = Depends(get_system_status_service),
) -> MaintenanceModeResponse:
    state = await service.enable_maintenance(
        request,
        actor_id=current_user.id,
        exclude_user_ids=[current_user.id],
    )
    return MaintenanceModeResponse(state=state)


@router.post(
    "/maintenance/disable",
    response_model=MaintenanceModeResponse,
    summary="Disable maintenance mode",
)
async def disable_maintenance_mode(
    current_user: User = Depends(require_admin_user),
    service: SystemStatusService = Depends(get_system_status_service),
) -> MaintenanceModeResponse:
    state = await service.disable_maintenance(actor_id=current_user.id)
    return MaintenanceModeResponse(state=state)


__all__ = ["router"]
