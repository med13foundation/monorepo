"""Listing and detail endpoints for admin templates."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from src.application.services.template_management_service import (
    TemplateManagementService,
)
from src.routes.admin_routes.dependencies import DEFAULT_OWNER_ID, get_template_service

from .schemas import (
    TemplateListResponse,
    TemplateResponse,
    TemplateScope,
)

router = APIRouter()


@router.get(
    "/templates",
    response_model=TemplateListResponse,
    summary="List available templates",
)
def list_templates(
    scope: TemplateScope = Query(
        TemplateScope.AVAILABLE,
        description="Template listing scope",
    ),
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    service: TemplateManagementService = Depends(get_template_service),
) -> TemplateListResponse:
    """List templates with optional scope filtering."""
    owner_id = DEFAULT_OWNER_ID
    skip = (page - 1) * limit

    if scope == TemplateScope.PUBLIC:
        templates = service.get_public_templates(skip=skip, limit=limit)
    elif scope == TemplateScope.MINE:
        templates = service.get_user_templates(owner_id, skip=skip, limit=limit)
    else:
        templates = service.get_available_templates(owner_id, skip=skip, limit=limit)

    return TemplateListResponse(
        templates=[TemplateResponse.from_entity(tpl) for tpl in templates],
        total=len(templates),
        page=page,
        limit=limit,
        scope=scope,
    )


@router.get(
    "/templates/{template_id}",
    response_model=TemplateResponse,
    summary="Get template details",
)
def get_template_detail(
    template_id: UUID,
    service: TemplateManagementService = Depends(get_template_service),
) -> TemplateResponse:
    """Retrieve a single template."""
    template = service.get_template(template_id)
    if template is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template not found",
        )
    return TemplateResponse.from_entity(template)


__all__ = ["router"]
