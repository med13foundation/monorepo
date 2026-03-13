"""Graph search routes for the standalone graph service."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from services.graph_api.auth import get_current_active_user
from services.graph_api.database import get_session
from services.graph_api.dependencies import (
    get_graph_search_service,
    get_space_access_port,
    verify_space_membership,
)
from src.application.agents.services.graph_search_service import GraphSearchService
from src.application.services.claim_first_metrics import (
    emit_graph_filter_preset_usage,
)
from src.domain.agents.contracts.graph_search import GraphSearchContract
from src.domain.entities.user import User
from src.domain.ports.space_access_port import SpaceAccessPort

router = APIRouter(prefix="/v1/spaces", tags=["graph-search"])


class GraphSearchRequest(BaseModel):
    """Request payload for graph search operations."""

    model_config = ConfigDict(strict=True)

    question: str = Field(..., min_length=1, max_length=2000)
    model_id: str | None = Field(default=None, min_length=1, max_length=128)
    max_depth: int = Field(default=2, ge=1, le=4)
    top_k: int = Field(default=25, ge=1, le=100)
    curation_statuses: list[str] | None = None
    include_evidence_chains: bool = Field(default=True)
    force_agent: bool = Field(default=False)


@router.post(
    "/{space_id}/graph/search",
    response_model=GraphSearchContract,
    summary="Search one graph space with a natural-language query",
)
async def search_graph(
    space_id: UUID,
    request: GraphSearchRequest,
    *,
    current_user: User = Depends(get_current_active_user),
    space_access: SpaceAccessPort = Depends(get_space_access_port),
    graph_search_service: GraphSearchService = Depends(get_graph_search_service),
    session: Session = Depends(get_session),
) -> GraphSearchContract:
    """Execute graph search in one graph space."""
    verify_space_membership(
        space_id=space_id,
        current_user=current_user,
        space_access=space_access,
        session=session,
    )
    emit_graph_filter_preset_usage(
        endpoint="graph_search",
        curation_statuses=request.curation_statuses,
    )

    try:
        return await graph_search_service.search(
            question=request.question,
            research_space_id=str(space_id),
            model_id=request.model_id,
            max_depth=request.max_depth,
            top_k=request.top_k,
            curation_statuses=request.curation_statuses,
            include_evidence_chains=request.include_evidence_chains,
            force_agent=request.force_agent,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Graph search failed: {exc!s}",
        ) from exc
    finally:
        await graph_search_service.close()


__all__ = ["GraphSearchRequest", "router", "search_graph"]
