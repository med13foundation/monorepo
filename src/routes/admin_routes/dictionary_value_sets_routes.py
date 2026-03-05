"""Value-set dictionary admin routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.domain.entities.user import User
from src.domain.ports import DictionaryPort
from src.routes.admin_routes.dependencies import get_admin_db_session

from .dictionary_route_common import get_dictionary_service, require_admin_user
from .dictionary_schemas import (
    ValueSetCreateRequest,
    ValueSetItemActiveRequest,
    ValueSetItemCreateRequest,
    ValueSetItemListResponse,
    ValueSetItemResponse,
    ValueSetListResponse,
    ValueSetResponse,
)

router = APIRouter()


@router.get(
    "/dictionary/value-sets",
    response_model=ValueSetListResponse,
    summary="List dictionary value sets",
)
async def list_dictionary_value_sets(
    variable_id: str | None = Query(
        default=None,
        description="Filter by variable ID",
    ),
    service: DictionaryPort = Depends(get_dictionary_service),
) -> ValueSetListResponse:
    value_sets = service.list_value_sets(variable_id=variable_id)
    return ValueSetListResponse(
        value_sets=[ValueSetResponse.from_model(vs) for vs in value_sets],
        total=len(value_sets),
    )


@router.post(
    "/dictionary/value-sets",
    response_model=ValueSetResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create dictionary value set",
)
async def create_dictionary_value_set(
    request: ValueSetCreateRequest,
    current_user: User = Depends(require_admin_user),
    session: Session = Depends(get_admin_db_session),
    service: DictionaryPort = Depends(get_dictionary_service),
) -> ValueSetResponse:
    try:
        value_set = service.create_value_set(
            value_set_id=request.id,
            variable_id=request.variable_id,
            name=request.name,
            description=request.description,
            external_ref=request.external_ref,
            is_extensible=request.is_extensible,
            created_by=f"manual:{current_user.id}",
            source_ref=request.source_ref,
        )
        session.commit()
        return ValueSetResponse.from_model(value_set)
    except IntegrityError as e:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Value set already exists or references invalid variable",
        ) from e
    except ValueError as e:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e


@router.get(
    "/dictionary/value-sets/{value_set_id}/items",
    response_model=ValueSetItemListResponse,
    summary="List dictionary value set items",
)
async def list_dictionary_value_set_items(
    value_set_id: str,
    include_inactive: bool = Query(
        default=False,
        description="Include inactive value set items",
    ),
    service: DictionaryPort = Depends(get_dictionary_service),
) -> ValueSetItemListResponse:
    items = service.list_value_set_items(
        value_set_id=value_set_id,
        include_inactive=include_inactive,
    )
    return ValueSetItemListResponse(
        items=[ValueSetItemResponse.from_model(item) for item in items],
        total=len(items),
    )


@router.post(
    "/dictionary/value-sets/{value_set_id}/items",
    response_model=ValueSetItemResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create dictionary value set item",
)
async def create_dictionary_value_set_item(
    value_set_id: str,
    request: ValueSetItemCreateRequest,
    current_user: User = Depends(require_admin_user),
    session: Session = Depends(get_admin_db_session),
    service: DictionaryPort = Depends(get_dictionary_service),
) -> ValueSetItemResponse:
    try:
        item = service.create_value_set_item(
            value_set_id=value_set_id,
            code=request.code,
            display_label=request.display_label,
            synonyms=request.synonyms,
            external_ref=request.external_ref,
            sort_order=request.sort_order,
            is_active=request.is_active,
            created_by=f"manual:{current_user.id}",
            source_ref=request.source_ref,
        )
        session.commit()
        return ValueSetItemResponse.from_model(item)
    except IntegrityError as e:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Value set item already exists or references invalid value set",
        ) from e
    except ValueError as e:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e


@router.patch(
    "/dictionary/value-set-items/{value_set_item_id}/active",
    response_model=ValueSetItemResponse,
    summary="Activate/deactivate a dictionary value set item",
)
async def set_dictionary_value_set_item_active(
    value_set_item_id: int,
    request: ValueSetItemActiveRequest,
    current_user: User = Depends(require_admin_user),
    session: Session = Depends(get_admin_db_session),
    service: DictionaryPort = Depends(get_dictionary_service),
) -> ValueSetItemResponse:
    try:
        item = service.set_value_set_item_active(
            value_set_item_id,
            is_active=request.is_active,
            reviewed_by=f"manual:{current_user.id}",
            revocation_reason=request.revocation_reason,
        )
        session.commit()
        return ValueSetItemResponse.from_model(item)
    except ValueError as e:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e


__all__ = ["router"]
