"""
Unified Search API routes for MED13 Resource Library.

Provides cross-entity search capabilities with relevance scoring.
"""

from collections.abc import Mapping, Sequence
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.application.search.search_service import (
    SearchEntity,
    SearchResultType,
    UnifiedSearchService,
)
from src.application.services.membership_management_service import (
    MembershipManagementService,
)
from src.database.session import get_session
from src.domain.entities.user import User
from src.infrastructure.dependency_injection.dependencies import (
    get_legacy_dependency_container,
)
from src.routes.auth import get_current_active_user
from src.routes.research_spaces.dependencies import (
    get_membership_service,
    verify_space_membership,
)
from src.type_definitions.common import JSONObject

router = APIRouter(prefix="/search", tags=["search"])


class SearchResultItem(BaseModel):
    """Typed representation of a unified search result."""

    entity_type: SearchResultType
    entity_id: str
    title: str
    description: str
    relevance_score: float = Field(ge=0.0)
    metadata: JSONObject


class UnifiedSearchResponse(BaseModel):
    """Unified search response payload."""

    query: str
    total_results: int
    entity_breakdown: dict[str, int]
    results: list[SearchResultItem]


class SearchSuggestionResponse(BaseModel):
    """Search suggestion payload."""

    query: str
    suggestions: list[str]
    total_suggestions: int


class SearchStatisticsResponse(BaseModel):
    """Search statistics payload."""

    total_entities: dict[str, int]
    searchable_fields: dict[str, list[str]]
    last_updated: str | None = None


def get_search_service(db: Session = Depends(get_session)) -> "UnifiedSearchService":
    """Dependency injection for unified search service."""
    # Get unified container with legacy support

    container = get_legacy_dependency_container()
    return container.create_unified_search_service(db)


@router.post(
    "/",
    summary="Unified search across all entities",
    response_model=UnifiedSearchResponse,
)
async def unified_search(
    space_id: UUID = Query(..., description="Research space scope"),
    query: str = Query(..., min_length=1, max_length=200, description="Search query"),
    *,
    entity_types: list[SearchEntity] | None = Query(
        None,
        description="Entity types to search (defaults to all)",
    ),
    limit: int = Query(20, ge=1, le=100, description="Maximum results per entity type"),
    current_user: User = Depends(get_current_active_user),
    membership_service: MembershipManagementService = Depends(get_membership_service),
    session: Session = Depends(get_session),
    service: UnifiedSearchService = Depends(get_search_service),
) -> UnifiedSearchResponse:
    """
    Perform unified search across kernel entities/observations/relations.

    Returns results sorted by relevance score with metadata for each entity type.
    """
    try:
        verify_space_membership(
            space_id,
            current_user.id,
            membership_service,
            session,
            current_user.role,
        )
        raw = service.search(
            research_space_id=str(space_id),
            query=query,
            entity_types=entity_types,
            limit=limit,
        )

        payload = raw if isinstance(raw, Mapping) else {}
        result_items = _build_search_results(payload.get("results"))
        query_field = payload.get("query")
        query_value = query_field if isinstance(query_field, str) else query

        total_results_value_obj = payload.get("total_results")
        total_results_value = (
            int(total_results_value_obj)
            if isinstance(total_results_value_obj, int | float)
            else len(result_items)
        )

        breakdown_value_obj = payload.get("entity_breakdown")
        breakdown_value = (
            _ensure_breakdown(breakdown_value_obj)
            if isinstance(breakdown_value_obj, Mapping)
            else {}
        )

        return UnifiedSearchResponse(
            query=query_value,
            total_results=total_results_value,
            entity_breakdown=breakdown_value,
            results=result_items,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search failed: {e!s}")


@router.get(
    "/suggest",
    summary="Search suggestions",
    response_model=SearchSuggestionResponse,
)
async def search_suggestions(
    query: str = Query(
        ...,
        min_length=1,
        max_length=50,
        description="Partial search query",
    ),
    limit: int = Query(10, ge=1, le=20, description="Maximum suggestions"),
    service: UnifiedSearchService = Depends(get_search_service),
) -> SearchSuggestionResponse:
    """
    Get search suggestions based on partial query input.

    Useful for autocomplete functionality in search interfaces.
    """
    try:
        # For now, return basic suggestions from recent/popular searches
        # In a full implementation, this would use search analytics
        suggestions = [
            f"{query} entities",
            f"{query} observations",
            f"{query} relations",
        ][:limit]

        return SearchSuggestionResponse(
            query=query,
            suggestions=suggestions,
            total_suggestions=len(suggestions),
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get suggestions: {e!s}",
        )


@router.get(
    "/stats",
    summary="Search statistics",
    response_model=SearchStatisticsResponse,
)
async def search_statistics(
    space_id: UUID = Query(..., description="Research space scope"),
    current_user: User = Depends(get_current_active_user),
    membership_service: MembershipManagementService = Depends(get_membership_service),
    session: Session = Depends(get_session),
    service: UnifiedSearchService = Depends(get_search_service),
) -> SearchStatisticsResponse:
    """
    Get statistics about searchable entities in the system.

    Useful for understanding the scope of available data.
    """
    try:
        verify_space_membership(
            space_id,
            current_user.id,
            membership_service,
            session,
            current_user.role,
        )

        stats = service.get_statistics(str(space_id))
        return _build_statistics_response(stats)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get search statistics: {e!s}",
        )


def _build_search_results(raw_results: object) -> list[SearchResultItem]:
    if not isinstance(raw_results, Sequence):
        return []
    items: list[SearchResultItem] = []
    for entry in raw_results:
        if not isinstance(entry, Mapping):
            continue
        entity_type_value = entry.get("entity_type")
        try:
            entity_type = SearchResultType(str(entity_type_value))
        except ValueError:
            continue
        entity_id_value = entry.get("entity_id")
        title_value = entry.get("title")
        description_value = entry.get("description")
        relevance_value = entry.get("relevance_score")
        metadata_value = entry.get("metadata")

        if not isinstance(title_value, str) or not isinstance(description_value, str):
            continue
        if isinstance(relevance_value, int | float | str):
            try:
                relevance_score = float(relevance_value)
            except (TypeError, ValueError):
                relevance_score = 0.0
        else:
            relevance_score = 0.0

        metadata_payload = metadata_value if isinstance(metadata_value, dict) else {}
        items.append(
            SearchResultItem(
                entity_type=entity_type,
                entity_id=str(entity_id_value),
                title=title_value,
                description=description_value,
                relevance_score=relevance_score,
                metadata=metadata_payload,
            ),
        )
    return items


def _ensure_breakdown(raw_breakdown: Mapping[str, object]) -> dict[str, int]:
    breakdown: dict[str, int] = {}
    for key, value in raw_breakdown.items():
        if isinstance(key, str) and isinstance(value, int | float):
            breakdown[key] = int(value)
    return breakdown


def _build_statistics_response(stats: Mapping[str, object]) -> SearchStatisticsResponse:
    total_entities_raw = stats.get("total_entities")
    searchable_fields_raw = stats.get("searchable_fields")
    last_updated = stats.get("last_updated")

    total_entities = (
        {
            key: int(val)
            for key, val in total_entities_raw.items()
            if isinstance(key, str) and isinstance(val, int | float)
        }
        if isinstance(total_entities_raw, Mapping)
        else {}
    )
    searchable_fields = (
        {
            key: [str(item) for item in value if isinstance(item, str)]
            for key, value in searchable_fields_raw.items()
            if isinstance(key, str) and isinstance(value, Sequence)
        }
        if isinstance(searchable_fields_raw, Mapping)
        else {}
    )
    return SearchStatisticsResponse(
        total_entities=total_entities,
        searchable_fields=searchable_fields,
        last_updated=last_updated if isinstance(last_updated, str) else None,
    )
