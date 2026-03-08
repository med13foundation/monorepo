"""Admin transform-registry endpoints for dictionary governance."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from src.domain.entities.user import User
from src.domain.ports import DictionaryPort
from src.routes.admin_routes.dependencies import get_admin_db_session

from .dictionary import get_dictionary_service, require_admin_user
from .dictionary_transform_schemas import (
    TransformRegistryListResponse,
    TransformRegistryResponse,
    TransformVerificationResponse,
)

router = APIRouter(
    dependencies=[Depends(require_admin_user)],
    tags=["dictionary"],
)


@router.get(
    "/dictionary/transforms",
    response_model=TransformRegistryListResponse,
    summary="List transform registry",
)
def list_transform_registry(
    status_filter: str = Query("ACTIVE", alias="status"),
    include_inactive: bool = Query(False),
    production_only: bool = Query(False),
    service: DictionaryPort = Depends(get_dictionary_service),
) -> TransformRegistryListResponse:
    transforms = service.list_transforms(
        status=status_filter,
        include_inactive=include_inactive,
        production_only=production_only,
    )
    return TransformRegistryListResponse(
        transforms=[TransformRegistryResponse.from_model(t) for t in transforms],
        total=len(transforms),
    )


@router.post(
    "/dictionary/transforms/{transform_id}/verify",
    response_model=TransformVerificationResponse,
    summary="Run transform fixture verification",
)
def verify_transform_registry_entry(
    transform_id: str,
    service: DictionaryPort = Depends(get_dictionary_service),
) -> TransformVerificationResponse:
    try:
        verification = service.verify_transform(transform_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    return TransformVerificationResponse.from_model(verification)


@router.patch(
    "/dictionary/transforms/{transform_id}/promote",
    response_model=TransformRegistryResponse,
    summary="Promote transform to production use",
)
def promote_transform_registry_entry(
    transform_id: str,
    current_user: User = Depends(require_admin_user),
    session: Session = Depends(get_admin_db_session),
    service: DictionaryPort = Depends(get_dictionary_service),
) -> TransformRegistryResponse:
    try:
        transform = service.promote_transform(
            transform_id,
            reviewed_by=f"manual:{current_user.id}",
        )
        session.commit()
    except ValueError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return TransformRegistryResponse.from_model(transform)


__all__ = ["router"]
