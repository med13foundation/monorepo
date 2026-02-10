"""Phenotype lookup and search routes scoped to research spaces."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from fastapi import Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.database.session import get_session
from src.domain.entities.user import User
from src.models.api import PhenotypeResponse, PhenotypeSearchResult
from src.routes.auth import get_current_active_user
from src.routes.phenotypes import get_phenotype_service
from src.routes.research_spaces.dependencies import (
    get_membership_service,
    require_researcher_role,
)
from src.routes.serializers import serialize_phenotype

from .router import (
    HTTP_400_BAD_REQUEST,
    HTTP_500_INTERNAL_SERVER_ERROR,
    research_spaces_router,
)

if TYPE_CHECKING:
    from src.application.services import MembershipManagementService
    from src.application.services.phenotype_service import PhenotypeApplicationService


class PhenotypeSearchParams(BaseModel):
    query: str = Field(..., min_length=1, description="Search query")
    limit: int = Field(10, ge=1, le=100, description="Maximum number of results")
    category: str | None = Field(None, description="Filter by category")

    model_config = {"extra": "ignore"}


def _parse_ids(raw_ids: str) -> list[int]:
    parts = [part.strip() for part in raw_ids.split(",") if part.strip()]
    if not parts:
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail="At least one phenotype ID is required",
        )
    parsed: list[int] = []
    seen: set[int] = set()
    for part in parts:
        try:
            value = int(part)
        except ValueError as exc:
            raise HTTPException(
                status_code=HTTP_400_BAD_REQUEST,
                detail=f"Invalid phenotype ID '{part}'",
            ) from exc
        if value not in seen:
            parsed.append(value)
            seen.add(value)
    return parsed


def _require_researcher_access(
    space_id: UUID,
    current_user: User,
    membership_service: MembershipManagementService,
    session: Session,
) -> None:
    require_researcher_role(
        space_id,
        current_user.id,
        membership_service,
        session,
        current_user.role,
    )


@research_spaces_router.get(
    "/{space_id}/phenotypes/search",
    summary="Search phenotypes in a research space",
    response_model=PhenotypeSearchResult,
)
async def search_space_phenotypes(
    space_id: UUID,
    params: PhenotypeSearchParams = Depends(),
    current_user: User = Depends(get_current_active_user),
    membership_service: MembershipManagementService = Depends(get_membership_service),
    service: PhenotypeApplicationService = Depends(get_phenotype_service),
    session: Session = Depends(get_session),
) -> PhenotypeSearchResult:
    """
    Search phenotypes by name, HPO ID, term, synonyms, or definition within a space.
    """
    _require_researcher_access(space_id, current_user, membership_service, session)
    try:
        filters = {"research_space_id": str(space_id)}
        if params.category:
            filters["category"] = params.category
        phenotypes = service.search_phenotypes(params.query, params.limit, filters)
        return PhenotypeSearchResult(
            query=params.query,
            total_results=len(phenotypes),
            results=[serialize_phenotype(p) for p in phenotypes],
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to search phenotypes: {exc!s}",
        ) from exc


@research_spaces_router.get(
    "/{space_id}/phenotypes/lookup",
    summary="Lookup phenotypes by ID in a research space",
    response_model=list[PhenotypeResponse],
)
async def lookup_space_phenotypes(
    space_id: UUID,
    ids: str = Query(..., description="Comma-separated phenotype IDs"),
    current_user: User = Depends(get_current_active_user),
    membership_service: MembershipManagementService = Depends(get_membership_service),
    service: PhenotypeApplicationService = Depends(get_phenotype_service),
    session: Session = Depends(get_session),
) -> list[PhenotypeResponse]:
    """Return phenotype records for the provided IDs within a space."""
    _require_researcher_access(space_id, current_user, membership_service, session)
    phenotype_ids = _parse_ids(ids)
    try:
        filters = {"research_space_id": str(space_id)}
        phenotypes = service.get_phenotypes_by_ids(phenotype_ids, filters)
        return [serialize_phenotype(p) for p in phenotypes]
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to lookup phenotypes: {exc!s}",
        ) from exc
