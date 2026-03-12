"""Graph-connection discovery endpoints scoped to research spaces."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING
from uuid import UUID

from fastapi import Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from src.application.agents.services.graph_connection_service import (
    GraphConnectionOutcome,
    GraphConnectionService,
)
from src.application.services.kernel.hybrid_graph_errors import (
    ConstraintConfigMissingError,
    EmbeddingNotReadyError,
)
from src.application.services.kernel.kernel_relation_suggestion_service import (
    KernelRelationSuggestionService,
)
from src.database.session import get_session
from src.domain.entities.user import User
from src.infrastructure.dependency_injection.dependencies import (
    get_legacy_dependency_container,
)
from src.routes.auth import get_current_active_user
from src.routes.research_spaces.dependencies import (
    get_membership_service,
    require_researcher_role,
    verify_space_membership,
)
from src.routes.research_spaces.kernel_dependencies import (
    get_kernel_relation_suggestion_service,
)
from src.routes.research_spaces.kernel_schemas import (
    KernelRelationSuggestionConstraintCheckResponse,
    KernelRelationSuggestionListResponse,
    KernelRelationSuggestionRequest,
    KernelRelationSuggestionResponse,
    KernelRelationSuggestionScoreBreakdownResponse,
)

from .router import (
    HTTP_400_BAD_REQUEST,
    HTTP_500_INTERNAL_SERVER_ERROR,
    research_spaces_router,
)

if TYPE_CHECKING:
    from src.application.services.membership_management_service import (
        MembershipManagementService,
    )

_BLANK_SEED_ENTITY_IDS_ERROR = "seed_entity_ids cannot contain blank values"
_RELATION_SUGGESTIONS_ENABLED_ENV = "MED13_ENABLE_RELATION_SUGGESTIONS"
_TRUE_VALUES = {"1", "true", "yes", "on"}


def _is_relation_suggestions_enabled() -> bool:
    raw_value = os.getenv(_RELATION_SUGGESTIONS_ENABLED_ENV, "0")
    return raw_value.strip().lower() in _TRUE_VALUES


def _feature_disabled_error(flag_name: str) -> HTTPException:
    return HTTPException(
        status_code=HTTP_400_BAD_REQUEST,
        detail={
            "code": "FEATURE_DISABLED",
            "message": (
                "This endpoint is disabled. "
                f"Enable {flag_name}=1 to use constrained relation suggestions."
            ),
        },
    )


class GraphConnectionDiscoverRequest(BaseModel):
    """Request payload for graph-connection discovery runs."""

    model_config = ConfigDict(strict=True)

    seed_entity_ids: list[str] = Field(..., min_length=1, max_length=200)
    source_type: str = Field(default="clinvar", min_length=1, max_length=64)
    model_id: str | None = Field(default=None, min_length=1, max_length=128)
    relation_types: list[str] | None = None
    max_depth: int = Field(default=2, ge=1, le=4)
    shadow_mode: bool | None = None


class GraphConnectionSingleRequest(BaseModel):
    """Request payload for one graph-connection discovery run."""

    model_config = ConfigDict(strict=True)

    source_type: str = Field(default="clinvar", min_length=1, max_length=64)
    model_id: str | None = Field(default=None, min_length=1, max_length=128)
    relation_types: list[str] | None = None
    max_depth: int = Field(default=2, ge=1, le=4)
    shadow_mode: bool | None = None


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


def get_graph_connection_service(
    session: Session = Depends(get_session),
) -> GraphConnectionService:
    """Dependency provider for graph-connection application service."""
    container = get_legacy_dependency_container()
    return container.create_graph_connection_service(session)


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


@research_spaces_router.post(
    "/{space_id}/graph/connections/discover",
    response_model=GraphConnectionDiscoverResponse,
    summary="Discover graph connections for one or more seed entities",
)
async def discover_graph_connections(
    space_id: UUID,
    request: GraphConnectionDiscoverRequest,
    current_user: User = Depends(get_current_active_user),
    membership_service: MembershipManagementService = Depends(get_membership_service),
    graph_connection_service: GraphConnectionService = Depends(
        get_graph_connection_service,
    ),
    session: Session = Depends(get_session),
) -> GraphConnectionDiscoverResponse:
    """Run graph-connection discovery for multiple seed entities."""
    verify_space_membership(
        space_id,
        current_user.id,
        membership_service,
        session,
        current_user.role,
    )

    try:
        seed_entity_ids = _normalize_seed_entity_ids(request.seed_entity_ids)
        outcomes = [
            await graph_connection_service.discover_connections_for_seed(
                research_space_id=str(space_id),
                seed_entity_id=seed_entity_id,
                source_type=request.source_type,
                model_id=request.model_id,
                relation_types=request.relation_types,
                max_depth=request.max_depth,
                shadow_mode=request.shadow_mode,
            )
            for seed_entity_id in seed_entity_ids
        ]
        return _serialize_run(outcomes)
    except ValueError as exc:
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Graph connection discovery failed: {exc!s}",
        ) from exc


@research_spaces_router.post(
    "/{space_id}/entities/{entity_id}/connections",
    response_model=GraphConnectionOutcomeResponse,
    summary="Discover graph connections for one entity",
)
async def discover_entity_graph_connections(
    space_id: UUID,
    entity_id: UUID,
    request: GraphConnectionSingleRequest,
    current_user: User = Depends(get_current_active_user),
    membership_service: MembershipManagementService = Depends(get_membership_service),
    graph_connection_service: GraphConnectionService = Depends(
        get_graph_connection_service,
    ),
    session: Session = Depends(get_session),
) -> GraphConnectionOutcomeResponse:
    """Run graph-connection discovery for a single entity."""
    verify_space_membership(
        space_id,
        current_user.id,
        membership_service,
        session,
        current_user.role,
    )

    try:
        outcome = await graph_connection_service.discover_connections_for_seed(
            research_space_id=str(space_id),
            seed_entity_id=str(entity_id),
            source_type=request.source_type,
            model_id=request.model_id,
            relation_types=request.relation_types,
            max_depth=request.max_depth,
            shadow_mode=request.shadow_mode,
        )
        return _serialize_outcome(outcome)
    except ValueError as exc:
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Graph connection discovery failed: {exc!s}",
        ) from exc


@research_spaces_router.post(
    "/{space_id}/graph/relation-suggestions",
    response_model=KernelRelationSuggestionListResponse,
    summary="Suggest constrained missing relations using hybrid graph + embeddings",
)
def suggest_graph_relations(
    space_id: UUID,
    request: KernelRelationSuggestionRequest,
    current_user: User = Depends(get_current_active_user),
    membership_service: MembershipManagementService = Depends(get_membership_service),
    relation_suggestion_service: KernelRelationSuggestionService = Depends(
        get_kernel_relation_suggestion_service,
    ),
    session: Session = Depends(get_session),
) -> KernelRelationSuggestionListResponse:
    require_researcher_role(
        space_id,
        current_user.id,
        membership_service,
        session,
        current_user.role,
    )

    if not _is_relation_suggestions_enabled():
        raise _feature_disabled_error(_RELATION_SUGGESTIONS_ENABLED_ENV)

    try:
        suggestions = relation_suggestion_service.suggest_relations(
            research_space_id=str(space_id),
            source_entity_ids=[
                str(entity_id) for entity_id in request.source_entity_ids
            ],
            limit_per_source=request.limit_per_source,
            min_score=request.min_score,
            allowed_relation_types=request.allowed_relation_types,
            target_entity_types=request.target_entity_types,
            exclude_existing_relations=request.exclude_existing_relations,
        )
    except EmbeddingNotReadyError as exc:
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail={"code": "EMBEDDING_NOT_READY", "message": str(exc)},
        ) from exc
    except ConstraintConfigMissingError as exc:
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail={"code": "CONSTRAINT_CONFIG_MISSING", "message": str(exc)},
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    serialized = [
        KernelRelationSuggestionResponse(
            source_entity_id=item.source_entity_id,
            target_entity_id=item.target_entity_id,
            relation_type=item.relation_type,
            final_score=item.final_score,
            score_breakdown=KernelRelationSuggestionScoreBreakdownResponse(
                vector_score=item.score_breakdown.vector_score,
                graph_overlap_score=item.score_breakdown.graph_overlap_score,
                relation_prior_score=item.score_breakdown.relation_prior_score,
            ),
            constraint_check=KernelRelationSuggestionConstraintCheckResponse(
                passed=item.constraint_check.passed,
                source_entity_type=item.constraint_check.source_entity_type,
                relation_type=item.constraint_check.relation_type,
                target_entity_type=item.constraint_check.target_entity_type,
            ),
        )
        for item in suggestions
    ]
    return KernelRelationSuggestionListResponse(
        suggestions=serialized,
        total=len(serialized),
        limit_per_source=request.limit_per_source,
        min_score=request.min_score,
    )
