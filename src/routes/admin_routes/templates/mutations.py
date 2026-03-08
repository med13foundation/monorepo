"""Mutation endpoints for admin templates."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from src.application.services.template_management_service import (
    CreateTemplateRequest as ServiceCreateTemplateRequest,
)
from src.application.services.template_management_service import (
    TemplateManagementService,
)
from src.application.services.template_management_service import (
    UpdateTemplateRequest as ServiceUpdateTemplateRequest,
)
from src.domain.entities.source_template import TemplateUIConfig
from src.routes.admin_routes.dependencies import DEFAULT_OWNER_ID, get_template_service

from .schemas import (
    TemplateCreatePayload,
    TemplateResponse,
    TemplateUpdatePayload,
)

router = APIRouter()


@router.post(
    "/templates",
    response_model=TemplateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create template",
)
def create_template(
    payload: TemplateCreatePayload,
    service: TemplateManagementService = Depends(get_template_service),
) -> TemplateResponse:
    """Create a new source template."""
    owner_id = DEFAULT_OWNER_ID
    create_request = ServiceCreateTemplateRequest(
        creator_id=owner_id,
        name=payload.name,
        description=payload.description,
        category=payload.category,
        source_type=payload.source_type,
        schema_definition=payload.schema_definition,
        validation_rules=payload.validation_rules,
        ui_config=payload.ui_config or TemplateUIConfig(),
        tags=payload.tags,
        is_public=payload.is_public,
    )
    template = service.create_template(create_request)
    return TemplateResponse.from_entity(template)


@router.put(
    "/templates/{template_id}",
    response_model=TemplateResponse,
    summary="Update template",
)
def update_template(
    template_id: UUID,
    payload: TemplateUpdatePayload,
    service: TemplateManagementService = Depends(get_template_service),
) -> TemplateResponse:
    """Update an existing template."""
    owner_id = DEFAULT_OWNER_ID
    update_request = ServiceUpdateTemplateRequest(
        name=payload.name,
        description=payload.description,
        category=payload.category,
        schema_definition=payload.schema_definition,
        validation_rules=payload.validation_rules,
        ui_config=payload.ui_config,
        tags=payload.tags,
    )
    template = service.update_template(template_id, update_request, owner_id)
    if template is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template not found",
        )
    return TemplateResponse.from_entity(template)


@router.delete(
    "/templates/{template_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete template",
)
def delete_template(
    template_id: UUID,
    service: TemplateManagementService = Depends(get_template_service),
) -> None:
    """Delete a template."""
    owner_id = DEFAULT_OWNER_ID
    success = service.delete_template(template_id, owner_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template not found",
        )


@router.post(
    "/templates/{template_id}/public",
    response_model=TemplateResponse,
    summary="Make a template public",
)
def make_template_public(
    template_id: UUID,
    service: TemplateManagementService = Depends(get_template_service),
) -> TemplateResponse:
    """Mark a template as public."""
    template = service.make_template_public(template_id, DEFAULT_OWNER_ID)
    if template is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template not found",
        )
    return TemplateResponse.from_entity(template)


@router.post(
    "/templates/{template_id}/approve",
    response_model=TemplateResponse,
    summary="Approve a template for general use",
)
def approve_template(
    template_id: UUID,
    service: TemplateManagementService = Depends(get_template_service),
) -> TemplateResponse:
    """Mark a template as approved."""
    template = service.approve_template(template_id, DEFAULT_OWNER_ID)
    if template is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template not found",
        )
    return TemplateResponse.from_entity(template)


__all__ = ["router"]
