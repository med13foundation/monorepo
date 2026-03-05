"""Misc dictionary admin routes (search/changelog/policies/constraints/reembed)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from src.domain.entities.user import User
from src.domain.ports import DictionaryPort
from src.routes.admin_routes.dependencies import get_admin_db_session

from .dictionary_route_common import get_dictionary_service, require_admin_user
from .dictionary_schemas import (
    DictionaryChangelogListResponse,
    DictionaryChangelogResponse,
    DictionaryReembedRequest,
    DictionaryReembedResponse,
    DictionarySearchListResponse,
    DictionarySearchResultResponse,
    EntityResolutionPolicyListResponse,
    EntityResolutionPolicyResponse,
    KernelDictionaryDimension,
    RelationConstraintListResponse,
    RelationConstraintResponse,
)

router = APIRouter()


@router.get(
    "/dictionary/search",
    response_model=DictionarySearchListResponse,
    summary="Search dictionary entries",
)
async def search_dictionary_entries(
    terms: list[str] = Query(
        ...,
        description="Search terms (repeat parameter for multiple terms)",
    ),
    dimensions: list[KernelDictionaryDimension] | None = Query(
        default=None,
        description="Optional dictionary dimensions to search",
    ),
    domain_context: str | None = Query(
        default=None,
        description="Optional domain context filter",
    ),
    limit: int = Query(default=50, ge=1, le=500),
    service: DictionaryPort = Depends(get_dictionary_service),
) -> DictionarySearchListResponse:
    requested_dimensions = (
        [dimension.value for dimension in dimensions] if dimensions else None
    )
    results = service.dictionary_search(
        terms=terms,
        dimensions=requested_dimensions,
        domain_context=domain_context,
        limit=limit,
    )
    return DictionarySearchListResponse(
        results=[
            DictionarySearchResultResponse.from_model(result) for result in results
        ],
        total=len(results),
    )


@router.get(
    "/dictionary/search/by-domain/{domain_context}",
    response_model=DictionarySearchListResponse,
    summary="List dictionary entries by domain",
)
async def search_dictionary_entries_by_domain(
    domain_context: str,
    limit: int = Query(default=200, ge=1, le=500),
    service: DictionaryPort = Depends(get_dictionary_service),
) -> DictionarySearchListResponse:
    results = service.dictionary_search_by_domain(
        domain_context=domain_context,
        limit=limit,
    )
    return DictionarySearchListResponse(
        results=[
            DictionarySearchResultResponse.from_model(result) for result in results
        ],
        total=len(results),
    )


@router.post(
    "/dictionary/reembed",
    response_model=DictionaryReembedResponse,
    summary="Recompute dictionary description embeddings",
)
async def reembed_dictionary_descriptions(
    request: DictionaryReembedRequest,
    current_user: User = Depends(require_admin_user),
    session: Session = Depends(get_admin_db_session),
    service: DictionaryPort = Depends(get_dictionary_service),
) -> DictionaryReembedResponse:
    try:
        updated_records = service.reembed_descriptions(
            model_name=request.model_name,
            limit_per_dimension=request.limit_per_dimension,
            changed_by=f"manual:{current_user.id}",
            source_ref=request.source_ref,
        )
        session.commit()
        return DictionaryReembedResponse(
            updated_records=updated_records,
            model_name=request.model_name,
        )
    except ValueError as e:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e


@router.get(
    "/dictionary/resolution-policies",
    response_model=EntityResolutionPolicyListResponse,
    summary="List entity resolution policies",
)
async def list_entity_resolution_policies(
    service: DictionaryPort = Depends(get_dictionary_service),
) -> EntityResolutionPolicyListResponse:
    policies = service.list_resolution_policies()
    return EntityResolutionPolicyListResponse(
        policies=[EntityResolutionPolicyResponse.from_model(p) for p in policies],
        total=len(policies),
    )


@router.get(
    "/dictionary/relation-constraints",
    response_model=RelationConstraintListResponse,
    summary="List relation constraints",
)
async def list_relation_constraints(
    source_type: str | None = Query(None, description="Filter by source entity type"),
    relation_type: str | None = Query(
        None,
        description="Filter by relation type",
    ),
    service: DictionaryPort = Depends(get_dictionary_service),
) -> RelationConstraintListResponse:
    constraints = service.get_constraints(
        source_type=source_type,
        relation_type=relation_type,
    )
    return RelationConstraintListResponse(
        constraints=[RelationConstraintResponse.from_model(c) for c in constraints],
        total=len(constraints),
    )


@router.get(
    "/dictionary/changelog",
    response_model=DictionaryChangelogListResponse,
    summary="List dictionary changelog entries",
)
async def list_dictionary_changelog_entries(
    table_name: str | None = Query(
        default=None,
        description="Filter by dictionary table name",
    ),
    record_id: str | None = Query(
        default=None,
        description="Filter by dictionary record ID",
    ),
    limit: int = Query(default=100, ge=1, le=500),
    service: DictionaryPort = Depends(get_dictionary_service),
) -> DictionaryChangelogListResponse:
    changelog_entries = service.list_changelog_entries(
        table_name=table_name,
        record_id=record_id,
        limit=limit,
    )
    return DictionaryChangelogListResponse(
        changelog_entries=[
            DictionaryChangelogResponse.from_model(entry) for entry in changelog_entries
        ],
        total=len(changelog_entries),
    )


__all__ = ["router"]
