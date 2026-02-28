"""Graph search endpoints scoped to research spaces."""

from __future__ import annotations

from uuid import UUID

from fastapi import Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from src.application.agents.services.graph_search_service import GraphSearchService
from src.application.services.claim_first_metrics import (
    emit_graph_filter_preset_usage,
)
from src.application.services.membership_management_service import (
    MembershipManagementService,
)
from src.database.session import get_session
from src.domain.agents.contracts.graph_search import GraphSearchContract
from src.domain.entities.user import User
from src.infrastructure.dependency_injection.dependencies import (
    get_legacy_dependency_container,
)
from src.routes.auth import get_current_active_user
from src.routes.research_spaces.dependencies import (
    get_membership_service,
    verify_space_membership,
)

from .router import (
    HTTP_400_BAD_REQUEST,
    HTTP_500_INTERNAL_SERVER_ERROR,
    research_spaces_router,
)


class GraphSearchRequest(BaseModel):
    """Request payload for graph search operations."""

    model_config = ConfigDict(strict=True)

    question: str = Field(..., min_length=1, max_length=2000)
    max_depth: int = Field(default=2, ge=1, le=4)
    top_k: int = Field(default=25, ge=1, le=100)
    curation_statuses: list[str] | None = None
    include_evidence_chains: bool = Field(default=True)
    force_agent: bool = Field(default=False)


def get_graph_search_service(
    session: Session = Depends(get_session),
) -> GraphSearchService:
    """Dependency provider for graph-search application service."""
    container = get_legacy_dependency_container()
    return container.create_graph_search_service(session)


@research_spaces_router.post(
    "/{space_id}/graph/search",
    response_model=GraphSearchContract,
    summary="Search the kernel graph with a natural-language query",
)
async def search_graph(
    space_id: UUID,
    request: GraphSearchRequest,
    current_user: User = Depends(get_current_active_user),
    membership_service: MembershipManagementService = Depends(get_membership_service),
    graph_search_service: GraphSearchService = Depends(get_graph_search_service),
    session: Session = Depends(get_session),
) -> GraphSearchContract:
    """Execute graph search in one research space."""
    verify_space_membership(
        space_id,
        current_user.id,
        membership_service,
        session,
        current_user.role,
    )
    emit_graph_filter_preset_usage(
        endpoint="graph_search",
        curation_statuses=request.curation_statuses,
    )

    try:
        return await graph_search_service.search(
            question=request.question,
            research_space_id=str(space_id),
            max_depth=request.max_depth,
            top_k=request.top_k,
            curation_statuses=request.curation_statuses,
            include_evidence_chains=request.include_evidence_chains,
            force_agent=request.force_agent,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Graph search failed: {exc!s}",
        ) from exc
