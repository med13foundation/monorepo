"""Relation-type dictionary admin routes."""

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
    DictionaryRelationTypeCreateRequest,
    DictionaryRelationTypeListResponse,
    DictionaryRelationTypeResponse,
    VariableDefinitionReviewStatusRequest,
    VariableDefinitionRevokeRequest,
)

router = APIRouter()


@router.get(
    "/dictionary/relation-types",
    response_model=DictionaryRelationTypeListResponse,
    summary="List dictionary relation types",
)
def list_dictionary_relation_types(
    domain_context: str | None = Query(None, description="Filter by domain context"),
    service: DictionaryPort = Depends(get_dictionary_service),
) -> DictionaryRelationTypeListResponse:
    relation_types = service.list_relation_types(domain_context=domain_context)
    return DictionaryRelationTypeListResponse(
        relation_types=[
            DictionaryRelationTypeResponse.from_model(r) for r in relation_types
        ],
        total=len(relation_types),
    )


@router.get(
    "/dictionary/relation-types/{relation_type_id}",
    response_model=DictionaryRelationTypeResponse,
    summary="Get dictionary relation type",
)
def get_dictionary_relation_type(
    relation_type_id: str,
    service: DictionaryPort = Depends(get_dictionary_service),
) -> DictionaryRelationTypeResponse:
    relation_type = service.get_relation_type(relation_type_id)
    if relation_type is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Relation type '{relation_type_id}' not found",
        )
    return DictionaryRelationTypeResponse.from_model(relation_type)


@router.post(
    "/dictionary/relation-types",
    response_model=DictionaryRelationTypeResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create dictionary relation type",
)
def create_dictionary_relation_type(
    request: DictionaryRelationTypeCreateRequest,
    current_user: User = Depends(require_admin_user),
    session: Session = Depends(get_admin_db_session),
    service: DictionaryPort = Depends(get_dictionary_service),
) -> DictionaryRelationTypeResponse:
    try:
        relation_type = service.create_relation_type(
            relation_type=request.id,
            display_name=request.display_name,
            description=request.description,
            domain_context=request.domain_context,
            is_directional=request.is_directional,
            inverse_label=request.inverse_label,
            created_by=f"manual:{current_user.id}",
            source_ref=request.source_ref,
        )
        session.commit()
        return DictionaryRelationTypeResponse.from_model(relation_type)
    except IntegrityError as e:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Relation type already exists or references invalid domain context",
        ) from e
    except ValueError as e:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e


@router.patch(
    "/dictionary/relation-types/{relation_type_id}/review-status",
    response_model=DictionaryRelationTypeResponse,
    summary="Set dictionary relation type review status",
)
def set_dictionary_relation_type_review_status(
    relation_type_id: str,
    request: VariableDefinitionReviewStatusRequest,
    current_user: User = Depends(require_admin_user),
    session: Session = Depends(get_admin_db_session),
    service: DictionaryPort = Depends(get_dictionary_service),
) -> DictionaryRelationTypeResponse:
    try:
        relation_type = service.set_relation_type_review_status(
            relation_type_id,
            review_status=request.review_status.value,
            reviewed_by=f"manual:{current_user.id}",
            revocation_reason=request.revocation_reason,
        )
        session.commit()
        return DictionaryRelationTypeResponse.from_model(relation_type)
    except IntegrityError as e:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Relation type review-status update conflicts with active graph "
                "references or dictionary constraints"
            ),
        ) from e
    except ValueError as e:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e


@router.post(
    "/dictionary/relation-types/{relation_type_id}/revoke",
    response_model=DictionaryRelationTypeResponse,
    summary="Revoke dictionary relation type",
)
def revoke_dictionary_relation_type(
    relation_type_id: str,
    request: VariableDefinitionRevokeRequest,
    current_user: User = Depends(require_admin_user),
    session: Session = Depends(get_admin_db_session),
    service: DictionaryPort = Depends(get_dictionary_service),
) -> DictionaryRelationTypeResponse:
    try:
        relation_type = service.revoke_relation_type(
            relation_type_id,
            reason=request.reason,
            reviewed_by=f"manual:{current_user.id}",
        )
        session.commit()
        return DictionaryRelationTypeResponse.from_model(relation_type)
    except IntegrityError as e:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Relation type revoke conflicts with active graph references or "
                "dictionary constraints"
            ),
        ) from e
    except ValueError as e:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e


@router.post(
    "/dictionary/relation-types/{relation_type_id}/merge",
    response_model=DictionaryRelationTypeResponse,
    summary="Merge dictionary relation type into another",
)
def merge_dictionary_relation_type(
    relation_type_id: str,
    request: DictionaryMergeRequest,
    current_user: User = Depends(require_admin_user),
    session: Session = Depends(get_admin_db_session),
    service: DictionaryPort = Depends(get_dictionary_service),
) -> DictionaryRelationTypeResponse:
    try:
        relation_type = service.merge_relation_type(
            relation_type_id,
            request.target_id,
            reason=request.reason,
            reviewed_by=f"manual:{current_user.id}",
        )
        session.commit()
        return DictionaryRelationTypeResponse.from_model(relation_type)
    except ValueError as e:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e


__all__ = ["router"]
