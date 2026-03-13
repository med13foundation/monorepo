"""Relation suggestion routes for the standalone graph service."""

from __future__ import annotations

import os
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from services.graph_api.auth import get_current_active_user
from services.graph_api.database import get_session
from services.graph_api.dependencies import (
    get_kernel_relation_suggestion_service,
    get_space_access_port,
    require_space_role,
)
from src.application.services.kernel.hybrid_graph_errors import (
    ConstraintConfigMissingError,
    EmbeddingNotReadyError,
)
from src.application.services.kernel.kernel_relation_suggestion_service import (
    KernelRelationSuggestionService,
)
from src.domain.entities.research_space_membership import MembershipRole
from src.domain.entities.user import User
from src.domain.ports.space_access_port import SpaceAccessPort
from src.type_definitions.graph_service_contracts import (
    KernelRelationSuggestionConstraintCheckResponse,
    KernelRelationSuggestionListResponse,
    KernelRelationSuggestionRequest,
    KernelRelationSuggestionResponse,
    KernelRelationSuggestionScoreBreakdownResponse,
)

router = APIRouter(prefix="/v1/spaces", tags=["graph-relation-suggestions"])

_RELATION_SUGGESTIONS_ENABLED_ENV = "MED13_ENABLE_RELATION_SUGGESTIONS"
_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})


def _is_relation_suggestions_enabled() -> bool:
    raw_value = os.getenv(_RELATION_SUGGESTIONS_ENABLED_ENV, "0")
    return raw_value.strip().lower() in _TRUE_VALUES


def _feature_disabled_error(flag_name: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail={
            "code": "FEATURE_DISABLED",
            "message": (
                "This endpoint is disabled. "
                f"Enable {flag_name}=1 to use constrained relation suggestions."
            ),
        },
    )


@router.post(
    "/{space_id}/graph/relation-suggestions",
    response_model=KernelRelationSuggestionListResponse,
    summary="Suggest constrained missing relations using hybrid graph + embeddings",
)
def suggest_graph_relations(
    space_id: UUID,
    request: KernelRelationSuggestionRequest,
    *,
    current_user: User = Depends(get_current_active_user),
    space_access: SpaceAccessPort = Depends(get_space_access_port),
    relation_suggestion_service: KernelRelationSuggestionService = Depends(
        get_kernel_relation_suggestion_service,
    ),
    session: Session = Depends(get_session),
) -> KernelRelationSuggestionListResponse:
    """Suggest missing graph relations in one graph space."""
    require_space_role(
        space_id=space_id,
        current_user=current_user,
        space_access=space_access,
        session=session,
        required_role=MembershipRole.RESEARCHER,
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
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "EMBEDDING_NOT_READY", "message": str(exc)},
        ) from exc
    except ConstraintConfigMissingError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "CONSTRAINT_CONFIG_MISSING", "message": str(exc)},
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    return KernelRelationSuggestionListResponse(
        suggestions=[
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
        ],
        total=len(suggestions),
        limit_per_source=request.limit_per_source,
        min_score=request.min_score,
    )


__all__ = ["router", "suggest_graph_relations"]
