"""Claim graph overlay routes for participants and claim-to-claim relations."""

from __future__ import annotations

from uuid import UUID

from fastapi import Depends, HTTPException, Query
from sqlalchemy.orm import Session

from src.application.services.kernel import (
    KernelClaimParticipantBackfillService,
    KernelClaimParticipantService,
    KernelClaimRelationService,
    KernelReasoningPathService,
    KernelRelationClaimService,
)
from src.application.services.membership_management_service import (
    MembershipManagementService,
)
from src.database.session import get_session
from src.domain.entities.kernel.claim_relations import (
    ClaimRelationReviewStatus,
    ClaimRelationType,
)
from src.domain.entities.user import User
from src.domain.repositories.kernel.claim_relation_repository import (
    ClaimRelationConstraintError,
)
from src.routes.auth import get_current_active_user
from src.routes.research_spaces.claim_graph_schemas import (
    ClaimParticipantBackfillRequest,
    ClaimParticipantBackfillResponse,
    ClaimParticipantCoverageResponse,
    ClaimParticipantListResponse,
    ClaimParticipantResponse,
    ClaimRelationCreateRequest,
    ClaimRelationListResponse,
    ClaimRelationResponse,
    ClaimRelationReviewUpdateRequest,
)
from src.routes.research_spaces.dependencies import (
    get_membership_service,
    require_curator_role,
    require_researcher_role,
    verify_space_membership,
)
from src.routes.research_spaces.kernel_dependencies import (
    get_kernel_claim_participant_backfill_service,
    get_kernel_claim_participant_service,
    get_kernel_claim_relation_service,
    get_kernel_reasoning_path_service,
    get_kernel_relation_claim_service,
)
from src.routes.research_spaces.kernel_schemas import (
    KernelRelationClaimListResponse,
    KernelRelationClaimResponse,
)

from .router import (
    HTTP_400_BAD_REQUEST,
    HTTP_404_NOT_FOUND,
    HTTP_409_CONFLICT,
    research_spaces_router,
)


def _normalize_relation_type(value: str) -> ClaimRelationType:  # noqa: PLR0911
    normalized = value.strip().upper()
    if normalized == "SUPPORTS":
        return "SUPPORTS"
    if normalized == "CONTRADICTS":
        return "CONTRADICTS"
    if normalized == "REFINES":
        return "REFINES"
    if normalized == "CAUSES":
        return "CAUSES"
    if normalized == "UPSTREAM_OF":
        return "UPSTREAM_OF"
    if normalized == "DOWNSTREAM_OF":
        return "DOWNSTREAM_OF"
    if normalized == "SAME_AS":
        return "SAME_AS"
    if normalized == "GENERALIZES":
        return "GENERALIZES"
    if normalized == "INSTANCE_OF":
        return "INSTANCE_OF"
    msg = f"Unsupported relation_type '{value}'"
    raise ValueError(msg)


def _normalize_review_status(value: str) -> ClaimRelationReviewStatus:
    normalized = value.strip().upper()
    if normalized == "PROPOSED":
        return "PROPOSED"
    if normalized == "ACCEPTED":
        return "ACCEPTED"
    if normalized == "REJECTED":
        return "REJECTED"
    msg = f"Unsupported review_status '{value}'"
    raise ValueError(msg)


@research_spaces_router.get(
    "/{space_id}/claims/by-entity/{entity_id}",
    response_model=KernelRelationClaimListResponse,
    summary="List relation claims linked to an entity via structured participants",
)
def list_claims_by_entity(
    space_id: UUID,
    entity_id: UUID,
    *,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_active_user),
    membership_service: MembershipManagementService = Depends(get_membership_service),
    claim_participant_service: KernelClaimParticipantService = Depends(
        get_kernel_claim_participant_service,
    ),
    relation_claim_service: KernelRelationClaimService = Depends(
        get_kernel_relation_claim_service,
    ),
    session: Session = Depends(get_session),
) -> KernelRelationClaimListResponse:
    verify_space_membership(
        space_id,
        current_user.id,
        membership_service,
        session,
        current_user.role,
    )

    claim_ids = claim_participant_service.list_claim_ids_by_entity(
        research_space_id=str(space_id),
        entity_id=str(entity_id),
        limit=limit,
        offset=offset,
    )
    total = claim_participant_service.count_claims_by_entity(
        research_space_id=str(space_id),
        entity_id=str(entity_id),
    )

    claims = [
        claim
        for claim in relation_claim_service.list_claims_by_ids(claim_ids)
        if str(claim.research_space_id) == str(space_id)
    ]

    return KernelRelationClaimListResponse(
        claims=[KernelRelationClaimResponse.from_model(item) for item in claims],
        total=total,
        offset=offset,
        limit=limit,
    )


@research_spaces_router.get(
    "/{space_id}/claims/{claim_id}/participants",
    response_model=ClaimParticipantListResponse,
    summary="List structured participants for one claim",
)
def list_claim_participants(
    space_id: UUID,
    claim_id: UUID,
    *,
    current_user: User = Depends(get_current_active_user),
    membership_service: MembershipManagementService = Depends(get_membership_service),
    claim_participant_service: KernelClaimParticipantService = Depends(
        get_kernel_claim_participant_service,
    ),
    relation_claim_service: KernelRelationClaimService = Depends(
        get_kernel_relation_claim_service,
    ),
    session: Session = Depends(get_session),
) -> ClaimParticipantListResponse:
    verify_space_membership(
        space_id,
        current_user.id,
        membership_service,
        session,
        current_user.role,
    )

    claim = relation_claim_service.get_claim(str(claim_id))
    if claim is None or str(claim.research_space_id) != str(space_id):
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND,
            detail="Relation claim not found",
        )

    participants = claim_participant_service.list_participants_for_claim(str(claim_id))
    return ClaimParticipantListResponse(
        claim_id=claim_id,
        participants=[
            ClaimParticipantResponse.from_model(participant)
            for participant in participants
        ],
        total=len(participants),
    )


@research_spaces_router.post(
    "/{space_id}/claim-participants/backfill",
    response_model=ClaimParticipantBackfillResponse,
    summary="Backfill structured participants for existing relation claims",
)
def backfill_claim_participants(
    space_id: UUID,
    request: ClaimParticipantBackfillRequest,
    current_user: User = Depends(get_current_active_user),
    membership_service: MembershipManagementService = Depends(get_membership_service),
    backfill_service: KernelClaimParticipantBackfillService = Depends(
        get_kernel_claim_participant_backfill_service,
    ),
    session: Session = Depends(get_session),
) -> ClaimParticipantBackfillResponse:
    require_researcher_role(
        space_id,
        current_user.id,
        membership_service,
        session,
        current_user.role,
    )

    summary = backfill_service.backfill_for_space(
        research_space_id=str(space_id),
        dry_run=request.dry_run,
        limit=request.limit,
        offset=request.offset,
    )
    if request.dry_run:
        session.rollback()
    else:
        session.commit()
    return ClaimParticipantBackfillResponse(
        scanned_claims=summary.scanned_claims,
        created_participants=summary.created_participants,
        skipped_existing=summary.skipped_existing,
        unresolved_endpoints=summary.unresolved_endpoints,
        dry_run=summary.dry_run,
    )


@research_spaces_router.get(
    "/{space_id}/claim-participants/coverage",
    response_model=ClaimParticipantCoverageResponse,
    summary="Get participant coverage summary for relation claims",
)
def get_claim_participant_coverage(
    space_id: UUID,
    *,
    limit: int = Query(500, ge=1, le=5000),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_active_user),
    membership_service: MembershipManagementService = Depends(get_membership_service),
    backfill_service: KernelClaimParticipantBackfillService = Depends(
        get_kernel_claim_participant_backfill_service,
    ),
    session: Session = Depends(get_session),
) -> ClaimParticipantCoverageResponse:
    verify_space_membership(
        space_id,
        current_user.id,
        membership_service,
        session,
        current_user.role,
    )

    coverage = backfill_service.coverage_for_space(
        research_space_id=str(space_id),
        limit=limit,
        offset=offset,
    )
    denominator = max(1, coverage.total_claims * 2)
    unresolved_total = (
        coverage.unresolved_subject_endpoints + coverage.unresolved_object_endpoints
    )
    unresolved_rate = float(unresolved_total) / float(denominator)
    return ClaimParticipantCoverageResponse(
        total_claims=coverage.total_claims,
        claims_with_any_participants=coverage.claims_with_any_participants,
        claims_with_subject=coverage.claims_with_subject,
        claims_with_object=coverage.claims_with_object,
        unresolved_subject_endpoints=coverage.unresolved_subject_endpoints,
        unresolved_object_endpoints=coverage.unresolved_object_endpoints,
        unresolved_endpoint_rate=round(unresolved_rate, 6),
    )


@research_spaces_router.get(
    "/{space_id}/claim-relations",
    response_model=ClaimRelationListResponse,
    summary="List claim-to-claim relation edges",
)
def list_claim_relations(
    space_id: UUID,
    *,
    relation_type: str | None = Query(None),
    review_status: str | None = Query(None),
    source_claim_id: UUID | None = Query(None),
    target_claim_id: UUID | None = Query(None),
    claim_id: UUID | None = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_active_user),
    membership_service: MembershipManagementService = Depends(get_membership_service),
    claim_relation_service: KernelClaimRelationService = Depends(
        get_kernel_claim_relation_service,
    ),
    session: Session = Depends(get_session),
) -> ClaimRelationListResponse:
    verify_space_membership(
        space_id,
        current_user.id,
        membership_service,
        session,
        current_user.role,
    )

    normalized_relation_type = (
        _normalize_relation_type(relation_type)
        if relation_type is not None and relation_type.strip()
        else None
    )
    normalized_review_status = (
        _normalize_review_status(review_status)
        if review_status is not None and review_status.strip()
        else None
    )

    claim_relations = claim_relation_service.list_by_research_space(
        str(space_id),
        relation_type=normalized_relation_type,
        review_status=normalized_review_status,
        source_claim_id=str(source_claim_id) if source_claim_id is not None else None,
        target_claim_id=str(target_claim_id) if target_claim_id is not None else None,
        claim_id=str(claim_id) if claim_id is not None else None,
        limit=limit,
        offset=offset,
    )
    total = claim_relation_service.count_by_research_space(
        str(space_id),
        relation_type=normalized_relation_type,
        review_status=normalized_review_status,
        source_claim_id=str(source_claim_id) if source_claim_id is not None else None,
        target_claim_id=str(target_claim_id) if target_claim_id is not None else None,
        claim_id=str(claim_id) if claim_id is not None else None,
    )

    return ClaimRelationListResponse(
        claim_relations=[
            ClaimRelationResponse.from_model(item) for item in claim_relations
        ],
        total=total,
        offset=offset,
        limit=limit,
    )


@research_spaces_router.post(
    "/{space_id}/claim-relations",
    response_model=ClaimRelationResponse,
    summary="Create one claim-to-claim relation edge",
)
def create_claim_relation(
    space_id: UUID,
    request: ClaimRelationCreateRequest,
    current_user: User = Depends(get_current_active_user),
    membership_service: MembershipManagementService = Depends(get_membership_service),
    relation_claim_service: KernelRelationClaimService = Depends(
        get_kernel_relation_claim_service,
    ),
    claim_relation_service: KernelClaimRelationService = Depends(
        get_kernel_claim_relation_service,
    ),
    reasoning_path_service: KernelReasoningPathService = Depends(
        get_kernel_reasoning_path_service,
    ),
    session: Session = Depends(get_session),
) -> ClaimRelationResponse:
    require_researcher_role(
        space_id,
        current_user.id,
        membership_service,
        session,
        current_user.role,
    )

    source_claim = relation_claim_service.get_claim(str(request.source_claim_id))
    target_claim = relation_claim_service.get_claim(str(request.target_claim_id))
    if source_claim is None or str(source_claim.research_space_id) != str(space_id):
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND,
            detail="Source claim not found",
        )
    if target_claim is None or str(target_claim.research_space_id) != str(space_id):
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND,
            detail="Target claim not found",
        )

    try:
        relation = claim_relation_service.create_claim_relation(
            research_space_id=str(space_id),
            source_claim_id=str(request.source_claim_id),
            target_claim_id=str(request.target_claim_id),
            relation_type=_normalize_relation_type(request.relation_type),
            agent_run_id=request.agent_run_id,
            source_document_id=(
                str(request.source_document_id)
                if request.source_document_id is not None
                else None
            ),
            confidence=request.confidence,
            review_status=_normalize_review_status(request.review_status),
            evidence_summary=request.evidence_summary,
            metadata=request.metadata,
        )
        reasoning_path_service.mark_stale_for_claim_relation_ids(
            [str(relation.id)],
            str(space_id),
        )
        session.commit()
        return ClaimRelationResponse.from_model(relation)
    except ValueError as exc:
        session.rollback()
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except ClaimRelationConstraintError as exc:
        session.rollback()
        raise HTTPException(
            status_code=HTTP_409_CONFLICT,
            detail="Duplicate or invalid claim relation edge",
        ) from exc


@research_spaces_router.patch(
    "/{space_id}/claim-relations/{relation_id}",
    response_model=ClaimRelationResponse,
    summary="Update one claim relation review status",
)
def update_claim_relation_review_status(
    space_id: UUID,
    relation_id: UUID,
    request: ClaimRelationReviewUpdateRequest,
    current_user: User = Depends(get_current_active_user),
    membership_service: MembershipManagementService = Depends(get_membership_service),
    claim_relation_service: KernelClaimRelationService = Depends(
        get_kernel_claim_relation_service,
    ),
    reasoning_path_service: KernelReasoningPathService = Depends(
        get_kernel_reasoning_path_service,
    ),
    session: Session = Depends(get_session),
) -> ClaimRelationResponse:
    require_curator_role(
        space_id,
        current_user.id,
        membership_service,
        session,
        current_user.role,
    )

    existing = claim_relation_service.get_claim_relation(str(relation_id))
    if existing is None or str(existing.research_space_id) != str(space_id):
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND,
            detail="Claim relation not found",
        )

    try:
        updated = claim_relation_service.update_review_status(
            str(relation_id),
            review_status=_normalize_review_status(request.review_status),
        )
        reasoning_path_service.mark_stale_for_claim_relation_ids(
            [str(updated.id)],
            str(space_id),
        )
        session.commit()
        return ClaimRelationResponse.from_model(updated)
    except ValueError as exc:
        session.rollback()
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


__all__ = [
    "backfill_claim_participants",
    "create_claim_relation",
    "get_claim_participant_coverage",
    "list_claim_participants",
    "list_claim_relations",
    "list_claims_by_entity",
    "update_claim_relation_review_status",
]
