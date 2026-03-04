"""Concept Manager routes scoped to research spaces."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from fastapi import Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.application.services.membership_management_service import (
    MembershipManagementService,
)
from src.database.session import get_session
from src.domain.entities.user import User
from src.domain.ports.concept_port import ConceptPort
from src.routes.admin_routes.concept_schemas import (
    ConceptAliasListResponse,
    ConceptAliasResponse,
    ConceptDecisionListResponse,
    ConceptDecisionResponse,
    ConceptMemberListResponse,
    ConceptMemberResponse,
    ConceptPolicyResponse,
    ConceptSetListResponse,
    ConceptSetResponse,
)
from src.routes.auth import get_current_active_user
from src.routes.research_spaces.dependencies import (
    get_membership_service,
    require_curator_role,
    require_researcher_role,
    verify_space_membership,
)
from src.routes.research_spaces.kernel_dependencies import get_concept_service
from src.type_definitions.common import JSONObject

from .router import (
    HTTP_400_BAD_REQUEST,
    HTTP_409_CONFLICT,
    HTTP_500_INTERNAL_SERVER_ERROR,
    research_spaces_router,
)


class SpaceConceptSetCreateRequest(BaseModel):
    """Create concept set request scoped by route space_id."""

    model_config = ConfigDict(strict=True)

    name: str = Field(..., min_length=1, max_length=128)
    slug: str = Field(..., min_length=1, max_length=128)
    domain_context: str = Field(..., min_length=1, max_length=64)
    description: str | None = Field(default=None, max_length=4000)
    source_ref: str | None = Field(default=None, max_length=1024)


class SpaceConceptMemberCreateRequest(BaseModel):
    """Create concept member request scoped by route space_id."""

    model_config = ConfigDict(strict=True)

    concept_set_id: UUID
    domain_context: str = Field(..., min_length=1, max_length=64)
    canonical_label: str = Field(..., min_length=1, max_length=255)
    normalized_label: str = Field(..., min_length=1, max_length=255)
    sense_key: str = Field(default="", max_length=128)
    dictionary_dimension: str | None = Field(default=None, max_length=32)
    dictionary_entry_id: str | None = Field(default=None, max_length=128)
    is_provisional: bool = False
    metadata_payload: JSONObject = Field(default_factory=dict)
    source_ref: str | None = Field(default=None, max_length=1024)


class SpaceConceptAliasCreateRequest(BaseModel):
    """Create alias request scoped by route space_id."""

    model_config = ConfigDict(strict=True)

    concept_member_id: UUID
    domain_context: str = Field(..., min_length=1, max_length=64)
    alias_label: str = Field(..., min_length=1, max_length=255)
    alias_normalized: str = Field(..., min_length=1, max_length=255)
    source: str | None = Field(default=None, max_length=64)
    source_ref: str | None = Field(default=None, max_length=1024)


class SpaceConceptPolicyUpsertRequest(BaseModel):
    """Active concept policy upsert request."""

    model_config = ConfigDict(strict=True)

    mode: Literal["PRECISION", "BALANCED", "DISCOVERY"]
    minimum_edge_confidence: float = Field(default=0.6, ge=0.0, le=1.0)
    minimum_distinct_documents: int = Field(default=1, ge=1)
    allow_generic_relations: bool = True
    max_edges_per_document: int | None = Field(default=None, ge=1)
    policy_payload: JSONObject = Field(default_factory=dict)
    source_ref: str | None = Field(default=None, max_length=1024)


class SpaceConceptDecisionProposeRequest(BaseModel):
    """Concept decision proposal request scoped by route space_id."""

    model_config = ConfigDict(strict=True)

    decision_type: Literal[
        "CREATE",
        "MAP",
        "MERGE",
        "SPLIT",
        "LINK",
        "PROMOTE",
        "DEMOTE",
    ]
    decision_payload: JSONObject = Field(default_factory=dict)
    evidence_payload: JSONObject = Field(default_factory=dict)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    rationale: str | None = Field(default=None, max_length=4000)
    concept_set_id: UUID | None = None
    concept_member_id: UUID | None = None
    concept_link_id: UUID | None = None


class SpaceConceptDecisionStatusRequest(BaseModel):
    """Decision status update request."""

    model_config = ConfigDict(strict=True)

    decision_status: Literal[
        "PROPOSED",
        "NEEDS_REVIEW",
        "APPROVED",
        "REJECTED",
        "APPLIED",
    ]


def _verify_access(
    *,
    space_id: UUID,
    current_user: User,
    membership_service: MembershipManagementService,
    session: Session,
) -> None:
    verify_space_membership(
        space_id,
        current_user.id,
        membership_service,
        session,
        current_user.role,
    )


class _ConceptRouteContext:
    def __init__(
        self,
        *,
        current_user: User,
        membership_service: MembershipManagementService,
        service: ConceptPort,
        session: Session,
    ) -> None:
        self.current_user = current_user
        self.membership_service = membership_service
        self.service = service
        self.session = session


def get_concept_route_context(
    current_user: User = Depends(get_current_active_user),
    membership_service: MembershipManagementService = Depends(get_membership_service),
    service: ConceptPort = Depends(get_concept_service),
    session: Session = Depends(get_session),
) -> _ConceptRouteContext:
    return _ConceptRouteContext(
        current_user=current_user,
        membership_service=membership_service,
        service=service,
        session=session,
    )


@research_spaces_router.get(
    "/{space_id}/concepts/sets",
    response_model=ConceptSetListResponse,
    summary="List concept sets in a research space",
)
def list_concept_sets(
    space_id: UUID,
    include_inactive: bool = Query(False),
    current_user: User = Depends(get_current_active_user),
    membership_service: MembershipManagementService = Depends(get_membership_service),
    service: ConceptPort = Depends(get_concept_service),
    session: Session = Depends(get_session),
) -> ConceptSetListResponse:
    _verify_access(
        space_id=space_id,
        current_user=current_user,
        membership_service=membership_service,
        session=session,
    )
    concept_sets = service.list_concept_sets(
        research_space_id=str(space_id),
        include_inactive=include_inactive,
    )
    return ConceptSetListResponse(
        concept_sets=[ConceptSetResponse.from_model(item) for item in concept_sets],
        total=len(concept_sets),
    )


@research_spaces_router.get(
    "/{space_id}/concepts/members",
    response_model=ConceptMemberListResponse,
    summary="List concept members in a research space",
)
def list_concept_members(
    space_id: UUID,
    concept_set_id: UUID | None = Query(None),
    include_inactive: bool = Query(False),
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    context: _ConceptRouteContext = Depends(get_concept_route_context),
) -> ConceptMemberListResponse:
    _verify_access(
        space_id=space_id,
        current_user=context.current_user,
        membership_service=context.membership_service,
        session=context.session,
    )
    concept_members = context.service.list_concept_members(
        research_space_id=str(space_id),
        concept_set_id=(str(concept_set_id) if concept_set_id is not None else None),
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


@research_spaces_router.get(
    "/{space_id}/concepts/aliases",
    response_model=ConceptAliasListResponse,
    summary="List concept aliases in a research space",
)
def list_concept_aliases(
    space_id: UUID,
    concept_member_id: UUID | None = Query(None),
    include_inactive: bool = Query(False),
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    context: _ConceptRouteContext = Depends(get_concept_route_context),
) -> ConceptAliasListResponse:
    _verify_access(
        space_id=space_id,
        current_user=context.current_user,
        membership_service=context.membership_service,
        session=context.session,
    )
    concept_aliases = context.service.list_concept_aliases(
        research_space_id=str(space_id),
        concept_member_id=(
            str(concept_member_id) if concept_member_id is not None else None
        ),
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


@research_spaces_router.post(
    "/{space_id}/concepts/sets",
    response_model=ConceptSetResponse,
    summary="Create a concept set in a research space",
)
def create_concept_set(
    space_id: UUID,
    request: SpaceConceptSetCreateRequest,
    current_user: User = Depends(get_current_active_user),
    membership_service: MembershipManagementService = Depends(get_membership_service),
    service: ConceptPort = Depends(get_concept_service),
    session: Session = Depends(get_session),
) -> ConceptSetResponse:
    require_researcher_role(
        space_id,
        current_user.id,
        membership_service,
        session,
        current_user.role,
    )
    try:
        concept_set = service.create_concept_set(
            research_space_id=str(space_id),
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
            status_code=HTTP_409_CONFLICT,
            detail="Concept set conflicts with an existing active record",
        ) from exc
    except ValueError as exc:
        session.rollback()
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        session.rollback()
        raise HTTPException(
            status_code=HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Concept set creation failed: {exc!s}",
        ) from exc


@research_spaces_router.post(
    "/{space_id}/concepts/members",
    response_model=ConceptMemberResponse,
    summary="Create a concept member in a research space",
)
def create_concept_member(
    space_id: UUID,
    request: SpaceConceptMemberCreateRequest,
    current_user: User = Depends(get_current_active_user),
    membership_service: MembershipManagementService = Depends(get_membership_service),
    service: ConceptPort = Depends(get_concept_service),
    session: Session = Depends(get_session),
) -> ConceptMemberResponse:
    require_researcher_role(
        space_id,
        current_user.id,
        membership_service,
        session,
        current_user.role,
    )
    try:
        concept_member = service.create_concept_member(
            concept_set_id=str(request.concept_set_id),
            research_space_id=str(space_id),
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
            status_code=HTTP_409_CONFLICT,
            detail="Concept member conflicts with existing scoped uniqueness rules",
        ) from exc
    except ValueError as exc:
        session.rollback()
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@research_spaces_router.post(
    "/{space_id}/concepts/aliases",
    response_model=ConceptAliasResponse,
    summary="Create a concept alias in a research space",
)
def create_concept_alias(
    space_id: UUID,
    request: SpaceConceptAliasCreateRequest,
    current_user: User = Depends(get_current_active_user),
    membership_service: MembershipManagementService = Depends(get_membership_service),
    service: ConceptPort = Depends(get_concept_service),
    session: Session = Depends(get_session),
) -> ConceptAliasResponse:
    require_researcher_role(
        space_id,
        current_user.id,
        membership_service,
        session,
        current_user.role,
    )
    try:
        concept_alias = service.create_concept_alias(
            concept_member_id=str(request.concept_member_id),
            research_space_id=str(space_id),
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
            status_code=HTTP_409_CONFLICT,
            detail="Alias conflicts with existing active alias scope",
        ) from exc
    except ValueError as exc:
        session.rollback()
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@research_spaces_router.put(
    "/{space_id}/concepts/policy",
    response_model=ConceptPolicyResponse,
    summary="Upsert active concept policy for a research space",
)
def upsert_active_policy(
    space_id: UUID,
    request: SpaceConceptPolicyUpsertRequest,
    current_user: User = Depends(get_current_active_user),
    membership_service: MembershipManagementService = Depends(get_membership_service),
    service: ConceptPort = Depends(get_concept_service),
    session: Session = Depends(get_session),
) -> ConceptPolicyResponse:
    require_researcher_role(
        space_id,
        current_user.id,
        membership_service,
        session,
        current_user.role,
    )
    try:
        policy = service.upsert_active_policy(
            research_space_id=str(space_id),
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
            status_code=HTTP_409_CONFLICT,
            detail="Concept policy conflicts with active policy uniqueness",
        ) from exc
    except ValueError as exc:
        session.rollback()
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@research_spaces_router.get(
    "/{space_id}/concepts/policy",
    response_model=ConceptPolicyResponse | None,
    summary="Get active concept policy for a research space",
)
def get_active_policy(
    space_id: UUID,
    current_user: User = Depends(get_current_active_user),
    membership_service: MembershipManagementService = Depends(get_membership_service),
    service: ConceptPort = Depends(get_concept_service),
    session: Session = Depends(get_session),
) -> ConceptPolicyResponse | None:
    _verify_access(
        space_id=space_id,
        current_user=current_user,
        membership_service=membership_service,
        session=session,
    )
    policy = service.get_active_policy(research_space_id=str(space_id))
    if policy is None:
        return None
    return ConceptPolicyResponse.from_model(policy)


@research_spaces_router.post(
    "/{space_id}/concepts/decisions/propose",
    response_model=ConceptDecisionResponse,
    summary="Propose one concept decision in a research space",
)
def propose_concept_decision(
    space_id: UUID,
    request: SpaceConceptDecisionProposeRequest,
    current_user: User = Depends(get_current_active_user),
    membership_service: MembershipManagementService = Depends(get_membership_service),
    service: ConceptPort = Depends(get_concept_service),
    session: Session = Depends(get_session),
) -> ConceptDecisionResponse:
    require_researcher_role(
        space_id,
        current_user.id,
        membership_service,
        session,
        current_user.role,
    )
    try:
        decision = service.propose_decision(
            research_space_id=str(space_id),
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
            status_code=HTTP_409_CONFLICT,
            detail="Concept decision conflicts with existing records",
        ) from exc
    except ValueError as exc:
        session.rollback()
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@research_spaces_router.patch(
    "/{space_id}/concepts/decisions/{decision_id}/status",
    response_model=ConceptDecisionResponse,
    summary="Manually update a concept decision status",
)
def set_concept_decision_status(
    space_id: UUID,
    decision_id: str,
    request: SpaceConceptDecisionStatusRequest,
    current_user: User = Depends(get_current_active_user),
    membership_service: MembershipManagementService = Depends(get_membership_service),
    service: ConceptPort = Depends(get_concept_service),
    session: Session = Depends(get_session),
) -> ConceptDecisionResponse:
    require_curator_role(
        space_id,
        current_user.id,
        membership_service,
        session,
        current_user.role,
    )
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
            status_code=HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@research_spaces_router.get(
    "/{space_id}/concepts/decisions",
    response_model=ConceptDecisionListResponse,
    summary="List concept decisions in a research space",
)
def list_concept_decisions(
    space_id: UUID,
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
    context: _ConceptRouteContext = Depends(get_concept_route_context),
) -> ConceptDecisionListResponse:
    _verify_access(
        space_id=space_id,
        current_user=context.current_user,
        membership_service=context.membership_service,
        session=context.session,
    )
    concept_decisions = context.service.list_decisions(
        research_space_id=str(space_id),
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
