"""Graph-connection routes for the standalone graph service."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from services.graph_api.auth import get_current_active_user
from services.graph_api.database import get_session
from services.graph_api.dependencies import (
    get_graph_connection_service,
    get_space_access_port,
    verify_space_membership,
)
from src.application.agents.services.graph_connection_service import (
    GraphConnectionOutcome,
    GraphConnectionService,
)
from src.domain.agents.contracts.graph_connection import ProposedRelation
from src.domain.entities.user import User
from src.domain.ports.space_access_port import SpaceAccessPort

router = APIRouter(prefix="/v1/spaces", tags=["graph-connections"])

_BLANK_SEED_ENTITY_IDS_ERROR = "seed_entity_ids cannot contain blank values"


class GraphConnectionDiscoverRequest(BaseModel):
    """Request payload for graph-connection batch discovery runs."""

    model_config = ConfigDict(strict=True)

    seed_entity_ids: list[str] = Field(..., min_length=1, max_length=200)
    source_type: str | None = Field(default=None, min_length=1, max_length=64)
    source_id: str | None = Field(default=None, min_length=1, max_length=64)
    model_id: str | None = Field(default=None, min_length=1, max_length=128)
    relation_types: list[str] | None = None
    max_depth: int = Field(default=2, ge=1, le=4)
    shadow_mode: bool | None = None
    pipeline_run_id: str | None = Field(default=None, min_length=1, max_length=128)
    fallback_relations: list[ProposedRelation] | None = None


class GraphConnectionSingleRequest(BaseModel):
    """Request payload for one graph-connection discovery run."""

    model_config = ConfigDict(strict=True)

    source_type: str | None = Field(default=None, min_length=1, max_length=64)
    source_id: str | None = Field(default=None, min_length=1, max_length=64)
    model_id: str | None = Field(default=None, min_length=1, max_length=128)
    relation_types: list[str] | None = None
    max_depth: int = Field(default=2, ge=1, le=4)
    shadow_mode: bool | None = None
    pipeline_run_id: str | None = Field(default=None, min_length=1, max_length=128)
    fallback_relations: list[ProposedRelation] | None = None


class GraphConnectionOutcomeResponse(BaseModel):
    """Serialized graph-connection discovery outcome."""

    model_config = ConfigDict(strict=True)

    seed_entity_id: str
    research_space_id: str
    status: str
    reason: str
    review_required: bool
    shadow_mode: bool
    wrote_to_graph: bool
    run_id: str | None = None
    proposed_relations_count: int
    persisted_relations_count: int
    rejected_candidates_count: int
    errors: list[str]


class GraphConnectionDiscoverResponse(BaseModel):
    """Batch summary for graph-connection discovery runs."""

    model_config = ConfigDict(strict=True)

    requested: int
    processed: int
    discovered: int
    failed: int
    review_required: int
    shadow_runs: int
    proposed_relations_count: int
    persisted_relations_count: int
    rejected_candidates_count: int
    errors: list[str]
    outcomes: list[GraphConnectionOutcomeResponse]


def _serialize_outcome(
    outcome: GraphConnectionOutcome,
) -> GraphConnectionOutcomeResponse:
    return GraphConnectionOutcomeResponse(
        seed_entity_id=outcome.seed_entity_id,
        research_space_id=outcome.research_space_id,
        status=outcome.status,
        reason=outcome.reason,
        review_required=outcome.review_required,
        shadow_mode=outcome.shadow_mode,
        wrote_to_graph=outcome.wrote_to_graph,
        run_id=outcome.run_id,
        proposed_relations_count=outcome.proposed_relations_count,
        persisted_relations_count=outcome.persisted_relations_count,
        rejected_candidates_count=outcome.rejected_candidates_count,
        errors=list(outcome.errors),
    )


def _serialize_run(
    outcomes: list[GraphConnectionOutcome],
) -> GraphConnectionDiscoverResponse:
    serialized_outcomes = [_serialize_outcome(outcome) for outcome in outcomes]
    errors: list[str] = []
    for outcome in outcomes:
        errors.extend(list(outcome.errors))

    return GraphConnectionDiscoverResponse(
        requested=len(outcomes),
        processed=len(outcomes),
        discovered=sum(1 for outcome in outcomes if outcome.status == "discovered"),
        failed=sum(1 for outcome in outcomes if outcome.status == "failed"),
        review_required=sum(1 for outcome in outcomes if outcome.review_required),
        shadow_runs=sum(1 for outcome in outcomes if outcome.shadow_mode),
        proposed_relations_count=sum(
            outcome.proposed_relations_count for outcome in outcomes
        ),
        persisted_relations_count=sum(
            outcome.persisted_relations_count for outcome in outcomes
        ),
        rejected_candidates_count=sum(
            outcome.rejected_candidates_count for outcome in outcomes
        ),
        errors=errors,
        outcomes=serialized_outcomes,
    )


def _normalize_seed_entity_ids(seed_entity_ids: list[str]) -> list[str]:
    normalized_ids: list[str] = []
    for value in seed_entity_ids:
        normalized = value.strip()
        if not normalized:
            raise ValueError(_BLANK_SEED_ENTITY_IDS_ERROR)
        normalized_ids.append(str(UUID(normalized)))
    return normalized_ids


@router.post(
    "/{space_id}/graph/connections/discover",
    response_model=GraphConnectionDiscoverResponse,
    summary="Discover graph connections for one or more seed entities",
)
async def discover_graph_connections(
    space_id: UUID,
    request: GraphConnectionDiscoverRequest,
    *,
    current_user: User = Depends(get_current_active_user),
    space_access: SpaceAccessPort = Depends(get_space_access_port),
    graph_connection_service: GraphConnectionService = Depends(
        get_graph_connection_service,
    ),
    session: Session = Depends(get_session),
) -> GraphConnectionDiscoverResponse:
    """Run graph-connection discovery for multiple seed entities."""
    verify_space_membership(
        space_id=space_id,
        current_user=current_user,
        space_access=space_access,
        session=session,
    )

    try:
        seed_entity_ids = _normalize_seed_entity_ids(request.seed_entity_ids)
        outcomes = [
            await graph_connection_service.discover_connections_for_seed(
                research_space_id=str(space_id),
                seed_entity_id=seed_entity_id,
                source_id=request.source_id,
                source_type=request.source_type,
                model_id=request.model_id,
                relation_types=request.relation_types,
                max_depth=request.max_depth,
                shadow_mode=request.shadow_mode,
                pipeline_run_id=request.pipeline_run_id,
                fallback_relations=tuple(request.fallback_relations or ()),
            )
            for seed_entity_id in seed_entity_ids
        ]
        return _serialize_run(outcomes)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Graph connection discovery failed: {exc!s}",
        ) from exc
    finally:
        await graph_connection_service.close()


@router.post(
    "/{space_id}/entities/{entity_id}/connections",
    response_model=GraphConnectionOutcomeResponse,
    summary="Discover graph connections for one entity",
)
async def discover_entity_graph_connections(
    space_id: UUID,
    entity_id: UUID,
    request: GraphConnectionSingleRequest,
    *,
    current_user: User = Depends(get_current_active_user),
    space_access: SpaceAccessPort = Depends(get_space_access_port),
    graph_connection_service: GraphConnectionService = Depends(
        get_graph_connection_service,
    ),
    session: Session = Depends(get_session),
) -> GraphConnectionOutcomeResponse:
    """Run graph-connection discovery for a single entity."""
    verify_space_membership(
        space_id=space_id,
        current_user=current_user,
        space_access=space_access,
        session=session,
    )

    try:
        outcome = await graph_connection_service.discover_connections_for_seed(
            research_space_id=str(space_id),
            seed_entity_id=str(entity_id),
            source_id=request.source_id,
            source_type=request.source_type,
            model_id=request.model_id,
            relation_types=request.relation_types,
            max_depth=request.max_depth,
            shadow_mode=request.shadow_mode,
            pipeline_run_id=request.pipeline_run_id,
            fallback_relations=tuple(request.fallback_relations or ()),
        )
        return _serialize_outcome(outcome)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Graph connection discovery failed: {exc!s}",
        ) from exc
    finally:
        await graph_connection_service.close()


__all__ = [
    "GraphConnectionDiscoverRequest",
    "GraphConnectionDiscoverResponse",
    "GraphConnectionOutcomeResponse",
    "GraphConnectionSingleRequest",
    "discover_entity_graph_connections",
    "discover_graph_connections",
    "router",
]
