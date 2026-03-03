"""Entity-type dictionary admin routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.domain.entities.user import User
from src.domain.ports import DictionaryPort
from src.routes.admin_routes.dependencies import get_admin_db_session

from .dictionary_route_common import get_dictionary_service, require_admin_user
from .dictionary_schemas import (
    DictionaryEntityTypeCreateRequest,
    DictionaryEntityTypeListResponse,
    DictionaryEntityTypeResponse,
    DictionaryMergeRequest,
    VariableDefinitionReviewStatusRequest,
    VariableDefinitionRevokeRequest,
)

router = APIRouter()


@router.get(
    "/dictionary/entity-types",
    response_model=DictionaryEntityTypeListResponse,
    summary="List dictionary entity types",
)
async def list_dictionary_entity_types(
    domain_context: str | None = Query(None, description="Filter by domain context"),
    service: DictionaryPort = Depends(get_dictionary_service),
) -> DictionaryEntityTypeListResponse:
    entity_types = service.list_entity_types(domain_context=domain_context)
    return DictionaryEntityTypeListResponse(
        entity_types=[DictionaryEntityTypeResponse.from_model(e) for e in entity_types],
        total=len(entity_types),
    )


@router.get(
    "/dictionary/entity-types/{entity_type_id}",
    response_model=DictionaryEntityTypeResponse,
    summary="Get dictionary entity type",
)
async def get_dictionary_entity_type(
    entity_type_id: str,
    service: DictionaryPort = Depends(get_dictionary_service),
) -> DictionaryEntityTypeResponse:
    entity_type = service.get_entity_type(entity_type_id)
    if entity_type is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Entity type '{entity_type_id}' not found",
        )
    return DictionaryEntityTypeResponse.from_model(entity_type)


@router.post(
    "/dictionary/entity-types",
    response_model=DictionaryEntityTypeResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create dictionary entity type",
)
async def create_dictionary_entity_type(
    request: DictionaryEntityTypeCreateRequest,
    current_user: User = Depends(require_admin_user),
    session: Session = Depends(get_admin_db_session),
    service: DictionaryPort = Depends(get_dictionary_service),
) -> DictionaryEntityTypeResponse:
    try:
        entity_type = service.create_entity_type(
            entity_type=request.id,
            display_name=request.display_name,
            description=request.description,
            domain_context=request.domain_context,
            external_ontology_ref=request.external_ontology_ref,
            expected_properties=dict(request.expected_properties),
            created_by=f"manual:{current_user.id}",
            source_ref=request.source_ref,
        )
        session.commit()
        return DictionaryEntityTypeResponse.from_model(entity_type)
    except IntegrityError as e:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Entity type already exists or references invalid domain context",
        ) from e
    except ValueError as e:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e


@router.patch(
    "/dictionary/entity-types/{entity_type_id}/review-status",
    response_model=DictionaryEntityTypeResponse,
    summary="Set dictionary entity type review status",
)
async def set_dictionary_entity_type_review_status(
    entity_type_id: str,
    request: VariableDefinitionReviewStatusRequest,
    current_user: User = Depends(require_admin_user),
    session: Session = Depends(get_admin_db_session),
    service: DictionaryPort = Depends(get_dictionary_service),
) -> DictionaryEntityTypeResponse:
    try:
        entity_type = service.set_entity_type_review_status(
            entity_type_id,
            review_status=request.review_status.value,
            reviewed_by=f"manual:{current_user.id}",
            revocation_reason=request.revocation_reason,
        )
        session.commit()
        return DictionaryEntityTypeResponse.from_model(entity_type)
    except IntegrityError as e:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Entity type review-status update conflicts with active graph "
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
    "/dictionary/entity-types/{entity_type_id}/revoke",
    response_model=DictionaryEntityTypeResponse,
    summary="Revoke dictionary entity type",
)
async def revoke_dictionary_entity_type(
    entity_type_id: str,
    request: VariableDefinitionRevokeRequest,
    current_user: User = Depends(require_admin_user),
    session: Session = Depends(get_admin_db_session),
    service: DictionaryPort = Depends(get_dictionary_service),
) -> DictionaryEntityTypeResponse:
    try:
        entity_type = service.revoke_entity_type(
            entity_type_id,
            reason=request.reason,
            reviewed_by=f"manual:{current_user.id}",
        )
        session.commit()
        return DictionaryEntityTypeResponse.from_model(entity_type)
    except IntegrityError as e:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Entity type revoke conflicts with active graph references or "
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
    "/dictionary/entity-types/{entity_type_id}/merge",
    response_model=DictionaryEntityTypeResponse,
    summary="Merge dictionary entity type into another",
)
async def merge_dictionary_entity_type(
    entity_type_id: str,
    request: DictionaryMergeRequest,
    current_user: User = Depends(require_admin_user),
    session: Session = Depends(get_admin_db_session),
    service: DictionaryPort = Depends(get_dictionary_service),
) -> DictionaryEntityTypeResponse:
    try:
        entity_type = service.merge_entity_type(
            entity_type_id,
            request.target_id,
            reason=request.reason,
            reviewed_by=f"manual:{current_user.id}",
        )
        session.commit()
        return DictionaryEntityTypeResponse.from_model(entity_type)
    except ValueError as e:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e


__all__ = ["router"]
