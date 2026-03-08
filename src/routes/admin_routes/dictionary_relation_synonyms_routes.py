"""Relation-synonym dictionary admin routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.domain.entities.user import User
from src.domain.ports import DictionaryPort
from src.routes.admin_routes.dependencies import get_admin_db_session

from .dictionary_route_common import get_dictionary_service, require_admin_user
from .dictionary_schemas import (
    DictionaryRelationSynonymCreateRequest,
    DictionaryRelationSynonymListResponse,
    DictionaryRelationSynonymResponse,
    DictionaryRelationTypeResponse,
    VariableDefinitionReviewStatusRequest,
    VariableDefinitionRevokeRequest,
)

router = APIRouter()


@router.get(
    "/dictionary/relation-synonyms",
    response_model=DictionaryRelationSynonymListResponse,
    summary="List dictionary relation synonyms",
)
def list_dictionary_relation_synonyms(
    relation_type_id: str | None = Query(
        default=None,
        description="Filter by canonical relation type ID",
    ),
    include_inactive: bool = Query(
        default=False,
        description="Include inactive relation synonyms",
    ),
    service: DictionaryPort = Depends(get_dictionary_service),
) -> DictionaryRelationSynonymListResponse:
    relation_synonyms = service.list_relation_synonyms(
        relation_type_id=relation_type_id,
        include_inactive=include_inactive,
    )
    return DictionaryRelationSynonymListResponse(
        relation_synonyms=[
            DictionaryRelationSynonymResponse.from_model(synonym)
            for synonym in relation_synonyms
        ],
        total=len(relation_synonyms),
    )


@router.get(
    "/dictionary/relation-synonyms/resolve",
    response_model=DictionaryRelationTypeResponse,
    summary="Resolve relation synonym to canonical relation type",
)
def resolve_dictionary_relation_synonym(
    synonym: str = Query(..., description="Relation synonym to resolve"),
    include_inactive: bool = Query(
        default=False,
        description="Include inactive relation synonyms and relation types",
    ),
    service: DictionaryPort = Depends(get_dictionary_service),
) -> DictionaryRelationTypeResponse:
    relation_type = service.resolve_relation_synonym(
        synonym,
        include_inactive=include_inactive,
    )
    if relation_type is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Relation synonym '{synonym}' not found",
        )
    return DictionaryRelationTypeResponse.from_model(relation_type)


@router.post(
    "/dictionary/relation-synonyms",
    response_model=DictionaryRelationSynonymResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create dictionary relation synonym",
)
def create_dictionary_relation_synonym(
    request: DictionaryRelationSynonymCreateRequest,
    current_user: User = Depends(require_admin_user),
    session: Session = Depends(get_admin_db_session),
    service: DictionaryPort = Depends(get_dictionary_service),
) -> DictionaryRelationSynonymResponse:
    try:
        relation_synonym = service.create_relation_synonym(
            relation_type_id=request.relation_type_id,
            synonym=request.synonym,
            source=request.source,
            created_by=f"manual:{current_user.id}",
            source_ref=request.source_ref,
        )
        session.commit()
        return DictionaryRelationSynonymResponse.from_model(relation_synonym)
    except IntegrityError as e:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Relation synonym already exists, conflicts with another canonical "
                "relation type, or references an invalid relation type"
            ),
        ) from e
    except ValueError as e:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e


@router.patch(
    "/dictionary/relation-synonyms/{synonym_id}/review-status",
    response_model=DictionaryRelationSynonymResponse,
    summary="Set dictionary relation synonym review status",
)
def set_dictionary_relation_synonym_review_status(
    synonym_id: int,
    request: VariableDefinitionReviewStatusRequest,
    current_user: User = Depends(require_admin_user),
    session: Session = Depends(get_admin_db_session),
    service: DictionaryPort = Depends(get_dictionary_service),
) -> DictionaryRelationSynonymResponse:
    try:
        relation_synonym = service.set_relation_synonym_review_status(
            synonym_id,
            review_status=request.review_status.value,
            reviewed_by=f"manual:{current_user.id}",
            revocation_reason=request.revocation_reason,
        )
        session.commit()
        return DictionaryRelationSynonymResponse.from_model(relation_synonym)
    except IntegrityError as e:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Relation synonym review-status update conflicts with dictionary "
                "constraints"
            ),
        ) from e
    except ValueError as e:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e


@router.post(
    "/dictionary/relation-synonyms/{synonym_id}/revoke",
    response_model=DictionaryRelationSynonymResponse,
    summary="Revoke dictionary relation synonym",
)
def revoke_dictionary_relation_synonym(
    synonym_id: int,
    request: VariableDefinitionRevokeRequest,
    current_user: User = Depends(require_admin_user),
    session: Session = Depends(get_admin_db_session),
    service: DictionaryPort = Depends(get_dictionary_service),
) -> DictionaryRelationSynonymResponse:
    try:
        relation_synonym = service.revoke_relation_synonym(
            synonym_id,
            reason=request.reason,
            reviewed_by=f"manual:{current_user.id}",
        )
        session.commit()
        return DictionaryRelationSynonymResponse.from_model(relation_synonym)
    except IntegrityError as e:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Relation synonym revoke conflicts with dictionary constraints",
        ) from e
    except ValueError as e:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e


__all__ = ["router"]
