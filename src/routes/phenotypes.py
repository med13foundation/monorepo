"""
Phenotype API routes for MED13 Resource Library.

RESTful endpoints for phenotype management with HPO ontology integration.
"""

from collections.abc import Mapping
from enum import Enum
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.database.session import get_session
from src.infrastructure.dependency_injection.dependencies import (
    get_legacy_dependency_container,
)
from src.models.api import (
    PaginatedResponse,
    PhenotypeCategory,
    PhenotypeCategoryResult,
    PhenotypeCreate,
    PhenotypeEvidenceResponse,
    PhenotypeResponse,
    PhenotypeSearchResult,
    PhenotypeStatisticsResponse,
    PhenotypeUpdate,
)
from src.routes.serializers import serialize_phenotype
from src.type_definitions.common import PhenotypeUpdate as PhenotypeUpdatePayload


class PhenotypeListParams(BaseModel):
    page: int = Field(1, ge=1, description="Page number")
    per_page: int = Field(20, ge=1, le=100, description="Items per page")
    search: str | None = Field(
        None,
        description="Search by HPO ID, term, name, synonyms, or definition",
    )
    sort_by: str = Field("name", description="Sort field")
    sort_order: str = Field("asc", pattern="^(asc|desc)$", description="Sort order")
    category: str | None = Field(None, description="Filter by category")
    is_root_term: bool | None = Field(None, description="Filter by root terms")

    model_config = {"extra": "ignore"}


if TYPE_CHECKING:
    from src.application.services.phenotype_service import PhenotypeApplicationService

router = APIRouter(prefix="/phenotypes", tags=["phenotypes"])


def _stat_count(stats: Mapping[str, object], key: str) -> int:
    value = stats.get(key, 0)
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int | float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return 0
    return 0


def _enum_str(value: Enum | str) -> str:
    return value.value if isinstance(value, Enum) else str(value)


def _to_phenotype_update_payload(
    payload: PhenotypeUpdate,
) -> PhenotypeUpdatePayload:
    updates: PhenotypeUpdatePayload = {}
    if payload.name is not None:
        updates["name"] = payload.name
    if payload.definition is not None:
        updates["definition"] = payload.definition
    if payload.synonyms is not None:
        updates["synonyms"] = payload.synonyms
    if payload.category is not None:
        updates["category"] = _enum_str(payload.category)
    if payload.parent_hpo_id is not None:
        updates["parent_hpo_id"] = payload.parent_hpo_id
    if payload.is_root_term is not None:
        updates["is_root_term"] = payload.is_root_term
    if payload.frequency_in_med13 is not None:
        updates["frequency_in_med13"] = payload.frequency_in_med13
    if payload.severity_score is not None:
        updates["severity_score"] = payload.severity_score
    return updates


def get_phenotype_service(
    db: Session = Depends(get_session),
) -> "PhenotypeApplicationService":
    """Dependency injection for phenotype application service."""
    # Get unified container with legacy support

    container = get_legacy_dependency_container()
    return container.create_phenotype_application_service(db)


@router.get(
    "/",
    summary="List phenotypes",
    response_model=PaginatedResponse[PhenotypeResponse],
)
async def get_phenotypes(
    params: PhenotypeListParams = Depends(),
    service: "PhenotypeApplicationService" = Depends(get_phenotype_service),
) -> PaginatedResponse[PhenotypeResponse]:
    """
    Retrieve a paginated list of phenotypes with optional search and filters.
    """
    filters = {
        "category": params.category,
        "is_root_term": params.is_root_term,
    }
    filters = {k: v for k, v in filters.items() if v is not None}

    try:
        phenotypes, total = service.list_phenotypes(
            page=params.page,
            per_page=params.per_page,
            sort_by=params.sort_by,
            sort_order=params.sort_order,
            filters=filters,
        )

        phenotype_responses = [
            serialize_phenotype(phenotype) for phenotype in phenotypes
        ]

        total_pages = (total + params.per_page - 1) // params.per_page
        return PaginatedResponse(
            items=phenotype_responses,
            total=total,
            page=params.page,
            per_page=params.per_page,
            total_pages=total_pages,
            has_next=params.page < total_pages,
            has_prev=params.page > 1,
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve phenotypes: {e!s}",
        )


@router.get(
    "/{phenotype_id}",
    summary="Get phenotype by ID",
    response_model=PhenotypeResponse,
)
async def get_phenotype(
    phenotype_id: int,
    service: "PhenotypeApplicationService" = Depends(get_phenotype_service),
) -> PhenotypeResponse:
    """
    Retrieve a specific phenotype by its database ID.
    """
    try:
        # For now, we'll use get_by_id - may need to enhance service later
        phenotype = service.get_phenotype_by_hpo_id(
            f"HP:{phenotype_id:07d}",
        )  # Convert to HPO format
        if not phenotype:
            raise HTTPException(
                status_code=404,
                detail=f"Phenotype {phenotype_id} not found",
            )
        return serialize_phenotype(phenotype)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve phenotype: {e!s}",
        )


@router.get(
    "/hpo/{hpo_id}",
    summary="Get phenotype by HPO ID",
    response_model=PhenotypeResponse,
)
async def get_phenotype_by_hpo_id(
    hpo_id: str,
    service: "PhenotypeApplicationService" = Depends(get_phenotype_service),
) -> PhenotypeResponse:
    """
    Retrieve a specific phenotype by its HPO identifier.
    """
    try:
        phenotype = service.get_phenotype_by_hpo_id(hpo_id)
        if not phenotype:
            raise HTTPException(
                status_code=404,
                detail=f"Phenotype with HPO ID {hpo_id} not found",
            )
        return serialize_phenotype(phenotype)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve phenotype: {e!s}",
        )


@router.post(
    "/",
    summary="Create new phenotype",
    response_model=PhenotypeResponse,
    status_code=201,
)
async def create_phenotype(
    phenotype_data: PhenotypeCreate,
    service: "PhenotypeApplicationService" = Depends(get_phenotype_service),
) -> PhenotypeResponse:
    """
    Create a new phenotype.
    """
    try:
        phenotype = service.create_phenotype(
            hpo_id=phenotype_data.hpo_id,
            name=phenotype_data.name,
            definition=phenotype_data.definition,
            category=phenotype_data.category,
            synonyms=phenotype_data.synonyms,
        )

        return serialize_phenotype(phenotype)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create phenotype: {e!s}",
        )


@router.put(
    "/{phenotype_id}",
    summary="Update phenotype",
    response_model=PhenotypeResponse,
)
async def update_phenotype(
    phenotype_id: int,
    phenotype_data: PhenotypeUpdate,
    service: "PhenotypeApplicationService" = Depends(get_phenotype_service),
) -> PhenotypeResponse:
    """
    Update an existing phenotype by its database ID.
    """
    try:
        # Validate phenotype exists
        if not service.validate_phenotype_exists(phenotype_id):
            raise HTTPException(
                status_code=404,
                detail=f"Phenotype {phenotype_id} not found",
            )

        updates = _to_phenotype_update_payload(phenotype_data)

        phenotype = service.update_phenotype(phenotype_id, updates)
        return serialize_phenotype(phenotype)
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update phenotype: {e!s}",
        )


@router.delete("/{phenotype_id}", summary="Delete phenotype", status_code=204)
async def delete_phenotype(
    phenotype_id: int,
    service: "PhenotypeApplicationService" = Depends(get_phenotype_service),
) -> None:
    """
    Delete a phenotype by its database ID.
    """
    try:
        if not service.validate_phenotype_exists(phenotype_id):
            raise HTTPException(
                status_code=404,
                detail=f"Phenotype {phenotype_id} not found",
            )

        # For now, implement soft delete or check dependencies
        # TODO: Implement proper deletion logic with dependency checks
        raise HTTPException(
            status_code=501,
            detail="Phenotype deletion not yet implemented - requires dependency analysis",
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete phenotype: {e!s}",
        )


@router.get(
    "/search/",
    summary="Search phenotypes",
    response_model=PhenotypeSearchResult,
)
async def search_phenotypes(
    query: str = Query(..., min_length=1, description="Search query"),
    limit: int = Query(10, ge=1, le=100, description="Maximum number of results"),
    category: str | None = Query(None, description="Filter by category"),
    service: "PhenotypeApplicationService" = Depends(get_phenotype_service),
) -> PhenotypeSearchResult:
    """
    Search phenotypes by name, HPO ID, HPO term, synonyms, or definition.
    """
    try:
        filters = {"category": category} if category else {}
        phenotypes = service.search_phenotypes(query, limit, filters)

        return PhenotypeSearchResult(
            query=query,
            total_results=len(phenotypes),
            results=[serialize_phenotype(p) for p in phenotypes],
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to search phenotypes: {e!s}",
        )


@router.get(
    "/category/{category}",
    summary="Get phenotypes by category",
    response_model=PhenotypeCategoryResult,
)
async def get_phenotypes_by_category(
    category: str,
    limit: int | None = Query(
        None,
        ge=1,
        le=100,
        description="Maximum number of results",
    ),
    service: "PhenotypeApplicationService" = Depends(get_phenotype_service),
) -> PhenotypeCategoryResult:
    """
    Retrieve phenotypes filtered by clinical category.
    """
    try:
        phenotypes = service.get_phenotypes_by_category(category)

        if limit:
            phenotypes = phenotypes[:limit]

        try:
            response_category = PhenotypeCategory(category)
        except ValueError:
            response_category = PhenotypeCategory.OTHER

        return PhenotypeCategoryResult(
            category=response_category,
            total_results=len(phenotypes),
            results=[serialize_phenotype(p) for p in phenotypes],
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve phenotypes for category {category}: {e!s}",
        )


@router.get(
    "/statistics/",
    summary="Get phenotype statistics",
    response_model=PhenotypeStatisticsResponse,
)
async def get_phenotype_statistics(
    service: "PhenotypeApplicationService" = Depends(get_phenotype_service),
) -> PhenotypeStatisticsResponse:
    """
    Retrieve statistics about phenotypes in the repository.
    """
    try:
        stats = service.get_phenotype_statistics()
        return PhenotypeStatisticsResponse(
            total_phenotypes=_stat_count(stats, "total_phenotypes"),
            root_terms=_stat_count(stats, "root_terms"),
            phenotypes_with_evidence=_stat_count(stats, "phenotypes_with_evidence"),
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve phenotype statistics: {e!s}",
        )


@router.get(
    "/{phenotype_id}/evidence",
    summary="Get evidence for a phenotype",
    response_model=PhenotypeEvidenceResponse,
)
async def get_phenotype_evidence(
    phenotype_id: int,
    service: "PhenotypeApplicationService" = Depends(get_phenotype_service),
) -> PhenotypeEvidenceResponse:
    """
    Retrieve all evidence associated with a specific phenotype.
    """
    try:
        if not service.validate_phenotype_exists(phenotype_id):
            raise HTTPException(
                status_code=404,
                detail=f"Phenotype {phenotype_id} not found",
            )

        # TODO: Implement evidence retrieval for phenotypes
        return PhenotypeEvidenceResponse(
            phenotype_id=phenotype_id,
            evidence=[],
            total_count=0,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve evidence for phenotype {phenotype_id}: {e!s}",
        )
