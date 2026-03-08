"""Variable dictionary admin routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.domain.entities.user import User
from src.domain.ports import DictionaryPort
from src.routes.admin_routes.dependencies import get_admin_db_session

from .dictionary_route_common import get_dictionary_service, require_admin_user
from .dictionary_schemas import (
    DictionaryMergeRequest,
    VariableDefinitionCreateRequest,
    VariableDefinitionListResponse,
    VariableDefinitionResponse,
    VariableDefinitionReviewStatusRequest,
    VariableDefinitionRevokeRequest,
)

router = APIRouter()


@router.get(
    "/dictionary/variables",
    response_model=VariableDefinitionListResponse,
    summary="List dictionary variables",
)
def list_dictionary_variables(
    domain_context: str | None = Query(None, description="Filter by domain context"),
    data_type: str | None = Query(None, description="Filter by kernel data type"),
    service: DictionaryPort = Depends(get_dictionary_service),
) -> VariableDefinitionListResponse:
    variables = service.list_variables(
        domain_context=domain_context,
        data_type=data_type,
    )
    return VariableDefinitionListResponse(
        variables=[VariableDefinitionResponse.from_model(v) for v in variables],
        total=len(variables),
    )


@router.post(
    "/dictionary/variables",
    response_model=VariableDefinitionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create dictionary variable",
)
def create_dictionary_variable(
    request: VariableDefinitionCreateRequest,
    current_user: User = Depends(require_admin_user),
    session: Session = Depends(get_admin_db_session),
    service: DictionaryPort = Depends(get_dictionary_service),
) -> VariableDefinitionResponse:
    try:
        variable = service.create_variable(
            variable_id=request.id,
            canonical_name=request.canonical_name,
            display_name=request.display_name,
            data_type=request.data_type.value,
            domain_context=request.domain_context,
            sensitivity=request.sensitivity.value,
            preferred_unit=request.preferred_unit,
            constraints=dict(request.constraints),
            description=request.description,
            created_by=f"manual:{current_user.id}",
            source_ref=request.source_ref,
        )
        session.commit()
        return VariableDefinitionResponse.from_model(variable)
    except IntegrityError as e:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Variable already exists",
        ) from e
    except ValueError as e:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e


@router.patch(
    "/dictionary/variables/{variable_id}/review-status",
    response_model=VariableDefinitionResponse,
    summary="Set dictionary variable review status",
)
def set_dictionary_variable_review_status(
    variable_id: str,
    request: VariableDefinitionReviewStatusRequest,
    current_user: User = Depends(require_admin_user),
    session: Session = Depends(get_admin_db_session),
    service: DictionaryPort = Depends(get_dictionary_service),
) -> VariableDefinitionResponse:
    try:
        variable = service.set_review_status(
            variable_id,
            review_status=request.review_status.value,
            reviewed_by=f"manual:{current_user.id}",
            revocation_reason=request.revocation_reason,
        )
        session.commit()
        return VariableDefinitionResponse.from_model(variable)
    except ValueError as e:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e


@router.post(
    "/dictionary/variables/{variable_id}/revoke",
    response_model=VariableDefinitionResponse,
    summary="Revoke dictionary variable",
)
def revoke_dictionary_variable(
    variable_id: str,
    request: VariableDefinitionRevokeRequest,
    current_user: User = Depends(require_admin_user),
    session: Session = Depends(get_admin_db_session),
    service: DictionaryPort = Depends(get_dictionary_service),
) -> VariableDefinitionResponse:
    try:
        variable = service.revoke_variable(
            variable_id,
            reason=request.reason,
            reviewed_by=f"manual:{current_user.id}",
        )
        session.commit()
        return VariableDefinitionResponse.from_model(variable)
    except ValueError as e:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e


@router.post(
    "/dictionary/variables/{variable_id}/merge",
    response_model=VariableDefinitionResponse,
    summary="Merge dictionary variable into another",
)
def merge_dictionary_variable(
    variable_id: str,
    request: DictionaryMergeRequest,
    current_user: User = Depends(require_admin_user),
    session: Session = Depends(get_admin_db_session),
    service: DictionaryPort = Depends(get_dictionary_service),
) -> VariableDefinitionResponse:
    try:
        variable = service.merge_variable_definition(
            variable_id,
            request.target_id,
            reason=request.reason,
            reviewed_by=f"manual:{current_user.id}",
        )
        session.commit()
        return VariableDefinitionResponse.from_model(variable)
    except ValueError as e:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e


__all__ = ["router"]
