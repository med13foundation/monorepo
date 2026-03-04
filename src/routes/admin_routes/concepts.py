"""Admin Concept Manager endpoints."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.domain.entities.user import User
from src.domain.ports.concept_port import ConceptPort
from src.routes.admin_routes.dependencies import get_admin_db_session

from .concept_route_common import get_concept_service, require_admin_user
from .concept_schemas import (
    ConceptAliasCreateRequest,
    ConceptAliasListResponse,
    ConceptAliasResponse,
    ConceptDecisionListResponse,
    ConceptDecisionProposeRequest,
    ConceptDecisionResponse,
    ConceptDecisionStatusRequest,
    ConceptMemberCreateRequest,
    ConceptMemberListResponse,
    ConceptMemberResponse,
    ConceptPolicyResponse,
    ConceptPolicyUpsertRequest,
    ConceptSetCreateRequest,
    ConceptSetListResponse,
    ConceptSetResponse,
)

router = APIRouter(
    dependencies=[Depends(require_admin_user)],
    tags=["concepts"],
)


@router.get(
    "/concepts/sets",
    response_model=ConceptSetListResponse,
    summary="List concept sets for one research space",
)
async def list_concept_sets(
    research_space_id: str = Query(..., description="Research space UUID"),
    include_inactive: bool = Query(False),
    service: ConceptPort = Depends(get_concept_service),
) -> ConceptSetListResponse:
    concept_sets = service.list_concept_sets(
        research_space_id=research_space_id,
        include_inactive=include_inactive,
    )
    return ConceptSetListResponse(
        concept_sets=[ConceptSetResponse.from_model(item) for item in concept_sets],
        total=len(concept_sets),
    )


@router.get(
    "/concepts/members",
    response_model=ConceptMemberListResponse,
    summary="List concept members for one research space",
)
async def list_concept_members(
    research_space_id: str = Query(..., description="Research space UUID"),
    concept_set_id: str | None = Query(None, description="Optional concept set UUID"),
    include_inactive: bool = Query(False),
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    service: ConceptPort = Depends(get_concept_service),
) -> ConceptMemberListResponse:
    concept_members = service.list_concept_members(
        research_space_id=research_space_id,
        concept_set_id=concept_set_id,
        include_inactive=include_inactive,
        offset=offset,
        limit=limit,
    )
    return ConceptMemberListResponse(
        concept_members=[
            ConceptMemberResponse.from_model(item) for item in concept_members
        ],
        total=len(concept_members),
    )


@router.get(
    "/concepts/aliases",
    response_model=ConceptAliasListResponse,
    summary="List concept aliases for one research space",
)
async def list_concept_aliases(
    research_space_id: str = Query(..., description="Research space UUID"),
    concept_member_id: str | None = Query(
        None,
        description="Optional concept member UUID",
    ),
    include_inactive: bool = Query(False),
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    service: ConceptPort = Depends(get_concept_service),
) -> ConceptAliasListResponse:
    concept_aliases = service.list_concept_aliases(
        research_space_id=research_space_id,
        concept_member_id=concept_member_id,
        include_inactive=include_inactive,
        offset=offset,
        limit=limit,
    )
    return ConceptAliasListResponse(
        concept_aliases=[
            ConceptAliasResponse.from_model(item) for item in concept_aliases
        ],
        total=len(concept_aliases),
    )


@router.get(
    "/concepts/policy",
    response_model=ConceptPolicyResponse | None,
    summary="Get active concept policy for one research space",
)
async def get_active_policy(
    research_space_id: str = Query(..., description="Research space UUID"),
    service: ConceptPort = Depends(get_concept_service),
) -> ConceptPolicyResponse | None:
    policy = service.get_active_policy(research_space_id=research_space_id)
    if policy is None:
        return None
    return ConceptPolicyResponse.from_model(policy)


@router.get(
    "/concepts/decisions",
    response_model=ConceptDecisionListResponse,
    summary="List concept decisions for one research space",
)
async def list_concept_decisions(
    research_space_id: str = Query(..., description="Research space UUID"),
    decision_status: (
        Literal[
            "PROPOSED",
            "NEEDS_REVIEW",
            "APPROVED",
            "REJECTED",
            "APPLIED",
        ]
        | None
    ) = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    service: ConceptPort = Depends(get_concept_service),
) -> ConceptDecisionListResponse:
    concept_decisions = service.list_decisions(
        research_space_id=research_space_id,
        decision_status=decision_status,
        offset=offset,
        limit=limit,
    )
    return ConceptDecisionListResponse(
        concept_decisions=[
            ConceptDecisionResponse.from_model(item) for item in concept_decisions
        ],
        total=len(concept_decisions),
    )


@router.post(
    "/concepts/sets",
    response_model=ConceptSetResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create one concept set",
)
async def create_concept_set(
    request: ConceptSetCreateRequest,
    current_user: User = Depends(require_admin_user),
    session: Session = Depends(get_admin_db_session),
    service: ConceptPort = Depends(get_concept_service),
) -> ConceptSetResponse:
    try:
        concept_set = service.create_concept_set(
            research_space_id=str(request.research_space_id),
            name=request.name,
            slug=request.slug,
            domain_context=request.domain_context,
            description=request.description,
            created_by=f"manual:{current_user.id}",
            source_ref=request.source_ref,
        )
        session.commit()
        return ConceptSetResponse.from_model(concept_set)
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Concept set conflicts with an existing active record",
        ) from exc
    except ValueError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.post(
    "/concepts/members",
    response_model=ConceptMemberResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create one concept member",
)
async def create_concept_member(
    request: ConceptMemberCreateRequest,
    current_user: User = Depends(require_admin_user),
    session: Session = Depends(get_admin_db_session),
    service: ConceptPort = Depends(get_concept_service),
) -> ConceptMemberResponse:
    try:
        concept_member = service.create_concept_member(
            concept_set_id=str(request.concept_set_id),
            research_space_id=str(request.research_space_id),
            domain_context=request.domain_context,
            canonical_label=request.canonical_label,
            normalized_label=request.normalized_label,
            sense_key=request.sense_key,
            dictionary_dimension=request.dictionary_dimension,
            dictionary_entry_id=request.dictionary_entry_id,
            is_provisional=request.is_provisional,
            metadata_payload=request.metadata_payload,
            created_by=f"manual:{current_user.id}",
            source_ref=request.source_ref,
        )
        session.commit()
        return ConceptMemberResponse.from_model(concept_member)
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Concept member conflicts with existing scoped uniqueness rules",
        ) from exc
    except ValueError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.post(
    "/concepts/aliases",
    response_model=ConceptAliasResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create one concept alias",
)
async def create_concept_alias(
    request: ConceptAliasCreateRequest,
    current_user: User = Depends(require_admin_user),
    session: Session = Depends(get_admin_db_session),
    service: ConceptPort = Depends(get_concept_service),
) -> ConceptAliasResponse:
    try:
        concept_alias = service.create_concept_alias(
            concept_member_id=str(request.concept_member_id),
            research_space_id=str(request.research_space_id),
            domain_context=request.domain_context,
            alias_label=request.alias_label,
            alias_normalized=request.alias_normalized,
            source=request.source,
            created_by=f"manual:{current_user.id}",
            source_ref=request.source_ref,
        )
        session.commit()
        return ConceptAliasResponse.from_model(concept_alias)
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Alias conflicts with existing active alias scope",
        ) from exc
    except ValueError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.put(
    "/concepts/policy",
    response_model=ConceptPolicyResponse,
    summary="Upsert active concept policy for one research space",
)
async def upsert_active_policy(
    request: ConceptPolicyUpsertRequest,
    current_user: User = Depends(require_admin_user),
    session: Session = Depends(get_admin_db_session),
    service: ConceptPort = Depends(get_concept_service),
) -> ConceptPolicyResponse:
    try:
        policy = service.upsert_active_policy(
            research_space_id=str(request.research_space_id),
            mode=request.mode,
            created_by=f"manual:{current_user.id}",
            minimum_edge_confidence=request.minimum_edge_confidence,
            minimum_distinct_documents=request.minimum_distinct_documents,
            allow_generic_relations=request.allow_generic_relations,
            max_edges_per_document=request.max_edges_per_document,
            policy_payload=request.policy_payload,
            source_ref=request.source_ref,
        )
        session.commit()
        return ConceptPolicyResponse.from_model(policy)
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Concept policy conflicts with active policy uniqueness",
        ) from exc
    except ValueError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.post(
    "/concepts/decisions/propose",
    response_model=ConceptDecisionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Propose one concept decision (harness-gated)",
)
async def propose_decision(
    request: ConceptDecisionProposeRequest,
    current_user: User = Depends(require_admin_user),
    session: Session = Depends(get_admin_db_session),
    service: ConceptPort = Depends(get_concept_service),
) -> ConceptDecisionResponse:
    try:
        decision = service.propose_decision(
            research_space_id=str(request.research_space_id),
            decision_type=request.decision_type,
            proposed_by=f"manual:{current_user.id}",
            decision_payload=request.decision_payload,
            evidence_payload=request.evidence_payload,
            confidence=request.confidence,
            rationale=request.rationale,
            concept_set_id=(
                str(request.concept_set_id)
                if request.concept_set_id is not None
                else None
            ),
            concept_member_id=(
                str(request.concept_member_id)
                if request.concept_member_id is not None
                else None
            ),
            concept_link_id=(
                str(request.concept_link_id)
                if request.concept_link_id is not None
                else None
            ),
        )
        session.commit()
        return ConceptDecisionResponse.from_model(decision)
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Concept decision conflicts with existing records",
        ) from exc
    except ValueError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.patch(
    "/concepts/decisions/{decision_id}/status",
    response_model=ConceptDecisionResponse,
    summary="Manually set concept decision status",
)
async def set_decision_status(
    decision_id: str,
    request: ConceptDecisionStatusRequest,
    current_user: User = Depends(require_admin_user),
    session: Session = Depends(get_admin_db_session),
    service: ConceptPort = Depends(get_concept_service),
) -> ConceptDecisionResponse:
    try:
        decision = service.set_decision_status(
            decision_id,
            decision_status=request.decision_status,
            decided_by=f"manual:{current_user.id}",
        )
        session.commit()
        return ConceptDecisionResponse.from_model(decision)
    except ValueError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


__all__ = [
    "get_admin_db_session",
    "get_concept_service",
    "require_admin_user",
    "router",
]
