"""Claim-ledger and claim-relation routes for the standalone graph service."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from services.graph_api._claim_paper_links import (
    resolve_claim_evidence_paper_links,
)
from services.graph_api._claim_relation_normalization import (
    normalize_relation_type as normalize_claim_relation_type,
)
from services.graph_api._claim_relation_normalization import (
    normalize_review_status,
)
from services.graph_api._dictionary_relation_types import (
    canonicalize_dictionary_relation_type,
)
from services.graph_api.auth import get_current_active_user
from services.graph_api.database import get_session
from services.graph_api.dependencies import (
    get_dictionary_service,
    get_kernel_claim_evidence_service,
    get_kernel_claim_participant_service,
    get_kernel_claim_relation_service,
    get_kernel_entity_service,
    get_kernel_reasoning_path_service,
    get_kernel_relation_claim_service,
    get_kernel_relation_projection_materialization_service,
    get_space_access_port,
    require_space_role,
    verify_space_membership,
)
from src.application.services.claim_first_metrics import increment_metric
from src.application.services.kernel.kernel_claim_evidence_service import (
    KernelClaimEvidenceService,
)
from src.application.services.kernel.kernel_claim_participant_service import (
    KernelClaimParticipantService,
)
from src.application.services.kernel.kernel_claim_relation_service import (
    KernelClaimRelationService,
)
from src.application.services.kernel.kernel_entity_service import KernelEntityService
from src.application.services.kernel.kernel_reasoning_path_service import (
    KernelReasoningPathService,
)
from src.application.services.kernel.kernel_relation_claim_service import (
    KernelRelationClaimService,
)
from src.application.services.kernel.kernel_relation_projection_materialization_service import (
    KernelRelationProjectionMaterializationService,
)
from src.domain.entities.research_space_membership import MembershipRole
from src.domain.entities.user import User
from src.domain.ports.dictionary_port import DictionaryPort
from src.domain.ports.space_access_port import SpaceAccessPort
from src.domain.repositories.kernel.claim_relation_repository import (
    ClaimRelationConstraintError,
)
from src.models.database.source_document import SourceDocumentModel
from src.type_definitions.graph_service_contracts import (
    ClaimParticipantListResponse,
    ClaimParticipantResponse,
    ClaimRelationCreateRequest,
    ClaimRelationListResponse,
    ClaimRelationResponse,
    ClaimRelationReviewUpdateRequest,
    KernelClaimEvidenceListResponse,
    KernelClaimEvidenceResponse,
    KernelRelationClaimCreateRequest,
    KernelRelationClaimListResponse,
    KernelRelationClaimResponse,
    KernelRelationClaimTriageRequest,
    KernelRelationConflictListResponse,
    KernelRelationConflictResponse,
)

router = APIRouter(prefix="/v1/spaces", tags=["claims"])

_CLAIM_STATUSES = frozenset({"OPEN", "NEEDS_MAPPING", "REJECTED", "RESOLVED"})
_CLAIM_VALIDATION_STATES = frozenset(
    {
        "ALLOWED",
        "FORBIDDEN",
        "UNDEFINED",
        "INVALID_COMPONENTS",
        "ENDPOINT_UNRESOLVED",
        "SELF_LOOP",
    },
)
_CLAIM_PERSISTABILITY = frozenset({"PERSISTABLE", "NON_PERSISTABLE"})
_CLAIM_POLARITIES = frozenset({"SUPPORT", "REFUTE", "UNCERTAIN", "HYPOTHESIS"})
_CERTAINTY_BANDS = frozenset({"HIGH", "MEDIUM", "LOW"})
_ClaimStatus = Literal["OPEN", "NEEDS_MAPPING", "REJECTED", "RESOLVED"]
_ClaimValidationState = Literal[
    "ALLOWED",
    "FORBIDDEN",
    "UNDEFINED",
    "INVALID_COMPONENTS",
    "ENDPOINT_UNRESOLVED",
    "SELF_LOOP",
]
_ClaimPersistability = Literal["PERSISTABLE", "NON_PERSISTABLE"]
_ClaimPolarity = Literal["SUPPORT", "REFUTE", "UNCERTAIN", "HYPOTHESIS"]
_CertaintyBand = Literal["HIGH", "MEDIUM", "LOW"]
_CLAIM_VALIDATION_STATE_MAP: dict[str, _ClaimValidationState] = {
    "ALLOWED": "ALLOWED",
    "FORBIDDEN": "FORBIDDEN",
    "UNDEFINED": "UNDEFINED",
    "INVALID_COMPONENTS": "INVALID_COMPONENTS",
    "ENDPOINT_UNRESOLVED": "ENDPOINT_UNRESOLVED",
    "SELF_LOOP": "SELF_LOOP",
}


def _normalize_claim_status_filter(status_value: str | None) -> _ClaimStatus | None:
    if status_value is None:
        return None
    normalized = status_value.strip().upper()
    if not normalized:
        return None
    if normalized not in _CLAIM_STATUSES:
        msg = "claim_status must be one of: OPEN, NEEDS_MAPPING, REJECTED, RESOLVED"
        raise ValueError(msg)
    if normalized == "OPEN":
        return "OPEN"
    if normalized == "NEEDS_MAPPING":
        return "NEEDS_MAPPING"
    if normalized == "REJECTED":
        return "REJECTED"
    return "RESOLVED"


def _normalize_claim_validation_state(
    value: str | None,
) -> _ClaimValidationState | None:
    if value is None:
        return None
    normalized = value.strip().upper()
    if not normalized:
        return None
    normalized_state = _CLAIM_VALIDATION_STATE_MAP.get(normalized)
    if normalized_state is None:
        msg = (
            "validation_state must be one of: ALLOWED, FORBIDDEN, UNDEFINED, "
            "INVALID_COMPONENTS, ENDPOINT_UNRESOLVED, SELF_LOOP"
        )
        raise ValueError(msg)
    return normalized_state


def _normalize_claim_persistability(
    value: str | None,
) -> _ClaimPersistability | None:
    if value is None:
        return None
    normalized = value.strip().upper()
    if not normalized:
        return None
    if normalized not in _CLAIM_PERSISTABILITY:
        msg = "persistability must be one of: PERSISTABLE, NON_PERSISTABLE"
        raise ValueError(msg)
    if normalized == "PERSISTABLE":
        return "PERSISTABLE"
    return "NON_PERSISTABLE"


def _normalize_claim_polarity(value: str | None) -> _ClaimPolarity | None:
    if value is None:
        return None
    normalized = value.strip().upper()
    if not normalized:
        return None
    if normalized not in _CLAIM_POLARITIES:
        msg = "polarity must be one of: SUPPORT, REFUTE, UNCERTAIN, HYPOTHESIS"
        raise ValueError(msg)
    if normalized == "SUPPORT":
        return "SUPPORT"
    if normalized == "REFUTE":
        return "REFUTE"
    if normalized == "UNCERTAIN":
        return "UNCERTAIN"
    return "HYPOTHESIS"


def _normalize_certainty_band(value: str | None) -> _CertaintyBand | None:
    if value is None:
        return None
    normalized = value.strip().upper()
    if not normalized:
        return None
    if normalized not in _CERTAINTY_BANDS:
        msg = "certainty_band must be one of: HIGH, MEDIUM, LOW"
        raise ValueError(msg)
    if normalized == "HIGH":
        return "HIGH"
    if normalized == "MEDIUM":
        return "MEDIUM"
    return "LOW"


def _normalize_claim_evidence_sentence_source(
    value: str | None,
) -> Literal["verbatim_span", "artana_generated"] | None:
    if value == "verbatim_span":
        return "verbatim_span"
    if value == "artana_generated":
        return "artana_generated"
    return None


def _normalize_claim_evidence_sentence_confidence(
    value: str | None,
) -> Literal["low", "medium", "high"] | None:
    if value == "low":
        return "low"
    if value == "medium":
        return "medium"
    if value == "high":
        return "high"
    return None


def _activate_dictionary_dependencies_for_claim(  # noqa: PLR0913
    *,
    dictionary_service: DictionaryPort,
    source_type: str,
    relation_type: str,
    target_type: str,
    reviewed_by: str,
    source_ref: str,
) -> None:
    source_entity = dictionary_service.get_entity_type(
        source_type,
        include_inactive=True,
    )
    if source_entity is None:
        msg = f"Dictionary entity type '{source_type}' not found."
        raise ValueError(msg)
    if source_entity.review_status != "ACTIVE":
        dictionary_service.set_entity_type_review_status(
            source_type,
            review_status="ACTIVE",
            reviewed_by=reviewed_by,
        )

    target_entity = dictionary_service.get_entity_type(
        target_type,
        include_inactive=True,
    )
    if target_entity is None:
        msg = f"Dictionary entity type '{target_type}' not found."
        raise ValueError(msg)
    if target_entity.review_status != "ACTIVE":
        dictionary_service.set_entity_type_review_status(
            target_type,
            review_status="ACTIVE",
            reviewed_by=reviewed_by,
        )

    relation = dictionary_service.get_relation_type(
        relation_type,
        include_inactive=True,
    )
    if relation is None:
        msg = f"Dictionary relation type '{relation_type}' not found."
        raise ValueError(msg)
    if relation.review_status != "ACTIVE":
        dictionary_service.set_relation_type_review_status(
            relation_type,
            review_status="ACTIVE",
            reviewed_by=reviewed_by,
        )

    dictionary_service.create_relation_constraint(
        source_type=source_type,
        relation_type=relation_type,
        target_type=target_type,
        is_allowed=True,
        requires_evidence=True,
        created_by=reviewed_by,
        source_ref=source_ref,
    )


@router.get(
    "/{space_id}/claims",
    response_model=KernelRelationClaimListResponse,
    summary="List relation claims in one graph space",
)
def list_claims(
    space_id: UUID,
    *,
    claim_status: str | None = Query(default=None),
    validation_state: str | None = Query(default=None),
    persistability: str | None = Query(default=None),
    polarity: str | None = Query(default=None),
    source_document_id: str | None = Query(default=None),
    relation_type: str | None = Query(default=None),
    linked_relation_id: str | None = Query(default=None),
    certainty_band: str | None = Query(default=None),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    current_user: User = Depends(get_current_active_user),
    space_access: SpaceAccessPort = Depends(get_space_access_port),
    relation_claim_service: KernelRelationClaimService = Depends(
        get_kernel_relation_claim_service,
    ),
    session: Session = Depends(get_session),
) -> KernelRelationClaimListResponse:
    verify_space_membership(
        space_id=space_id,
        current_user=current_user,
        space_access=space_access,
        session=session,
    )
    try:
        normalized_claim_status = _normalize_claim_status_filter(claim_status)
        normalized_validation_state = _normalize_claim_validation_state(
            validation_state,
        )
        normalized_persistability = _normalize_claim_persistability(persistability)
        normalized_polarity = _normalize_claim_polarity(polarity)
        normalized_certainty_band = _normalize_certainty_band(certainty_band)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    claims = relation_claim_service.list_by_research_space(
        str(space_id),
        claim_status=normalized_claim_status,
        validation_state=normalized_validation_state,
        persistability=normalized_persistability,
        polarity=normalized_polarity,
        source_document_id=source_document_id,
        relation_type=relation_type,
        linked_relation_id=linked_relation_id,
        certainty_band=normalized_certainty_band,
        limit=limit,
        offset=offset,
    )
    total = relation_claim_service.count_by_research_space(
        str(space_id),
        claim_status=normalized_claim_status,
        validation_state=normalized_validation_state,
        persistability=normalized_persistability,
        polarity=normalized_polarity,
        source_document_id=source_document_id,
        relation_type=relation_type,
        linked_relation_id=linked_relation_id,
        certainty_band=normalized_certainty_band,
    )
    return KernelRelationClaimListResponse(
        claims=[KernelRelationClaimResponse.from_model(claim) for claim in claims],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.post(
    "/{space_id}/claims",
    response_model=KernelRelationClaimResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create one unresolved relation claim",
)
def create_claim(  # noqa: PLR0915
    space_id: UUID,
    request: KernelRelationClaimCreateRequest,
    *,
    current_user: User = Depends(get_current_active_user),
    space_access: SpaceAccessPort = Depends(get_space_access_port),
    entity_service: KernelEntityService = Depends(get_kernel_entity_service),
    relation_claim_service: KernelRelationClaimService = Depends(
        get_kernel_relation_claim_service,
    ),
    claim_participant_service: KernelClaimParticipantService = Depends(
        get_kernel_claim_participant_service,
    ),
    claim_evidence_service: KernelClaimEvidenceService = Depends(
        get_kernel_claim_evidence_service,
    ),
    dictionary_service: DictionaryPort = Depends(get_dictionary_service),
    session: Session = Depends(get_session),
) -> KernelRelationClaimResponse:
    require_space_role(
        space_id=space_id,
        current_user=current_user,
        space_access=space_access,
        session=session,
        required_role=MembershipRole.RESEARCHER,
    )
    try:
        source_entity = entity_service.get_entity(str(request.source_entity_id))
        target_entity = entity_service.get_entity(str(request.target_entity_id))
        if (
            source_entity is None
            or target_entity is None
            or str(source_entity.research_space_id) != str(space_id)
            or str(target_entity.research_space_id) != str(space_id)
        ):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Source or target entity not found",
            )

        normalized_relation_type = canonicalize_dictionary_relation_type(
            dictionary_service,
            request.relation_type,
        )
        if not normalized_relation_type:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="relation_type is required",
            )

        relation_definition = dictionary_service.get_relation_type(
            normalized_relation_type,
            include_inactive=True,
        )
        has_evidence = any(
            (
                request.evidence_summary,
                request.evidence_sentence,
                request.source_document_ref,
            ),
        )
        if relation_definition is None:
            validation_state: _ClaimValidationState = "UNDEFINED"
            persistability: _ClaimPersistability = "NON_PERSISTABLE"
            validation_reason = "relation_type_not_found_in_dictionary"
        else:
            is_allowed = dictionary_service.is_relation_allowed(
                source_entity.entity_type,
                normalized_relation_type,
                target_entity.entity_type,
            )
            if not is_allowed:
                validation_state = "FORBIDDEN"
                persistability = "NON_PERSISTABLE"
                validation_reason = "relation_not_allowed_by_active_constraints"
            elif (
                dictionary_service.requires_evidence(
                    source_entity.entity_type,
                    normalized_relation_type,
                    target_entity.entity_type,
                )
                and not has_evidence
            ):
                validation_state = "INVALID_COMPONENTS"
                persistability = "NON_PERSISTABLE"
                validation_reason = "relation_requires_evidence"
            else:
                validation_state = "ALLOWED"
                persistability = "PERSISTABLE"
                validation_reason = "created_via_claim_api"

        claim = relation_claim_service.create_claim(
            research_space_id=str(space_id),
            source_document_id=None,
            source_document_ref=request.source_document_ref,
            agent_run_id=request.agent_run_id,
            source_type=source_entity.entity_type,
            relation_type=normalized_relation_type,
            target_type=target_entity.entity_type,
            source_label=source_entity.display_label,
            target_label=target_entity.display_label,
            confidence=request.confidence,
            validation_state=validation_state,
            validation_reason=validation_reason,
            persistability=persistability,
            claim_status="OPEN",
            polarity="SUPPORT",
            claim_text=request.claim_text,
            claim_section=None,
            linked_relation_id=None,
            metadata={
                **request.metadata,
                "origin": "claim_api",
                "source_entity_id": str(source_entity.id),
                "target_entity_id": str(target_entity.id),
            },
        )
        claim_id = str(claim.id)
        claim_participant_service.create_participant(
            claim_id=claim_id,
            research_space_id=str(space_id),
            role="SUBJECT",
            label=source_entity.display_label,
            entity_id=str(source_entity.id),
            position=0,
            qualifiers={"origin": "claim_api"},
        )
        claim_participant_service.create_participant(
            claim_id=claim_id,
            research_space_id=str(space_id),
            role="OBJECT",
            label=target_entity.display_label,
            entity_id=str(target_entity.id),
            position=1,
            qualifiers={"origin": "claim_api"},
        )
        if has_evidence:
            claim_evidence_service.create_evidence(
                claim_id=claim_id,
                source_document_id=None,
                source_document_ref=request.source_document_ref,
                agent_run_id=request.agent_run_id,
                sentence=request.evidence_sentence,
                sentence_source=_normalize_claim_evidence_sentence_source(
                    request.evidence_sentence_source,
                ),
                sentence_confidence=_normalize_claim_evidence_sentence_confidence(
                    request.evidence_sentence_confidence,
                ),
                sentence_rationale=request.evidence_sentence_rationale,
                figure_reference=None,
                table_reference=None,
                confidence=request.confidence,
                metadata={
                    "origin": "claim_api",
                    "evidence_summary": request.evidence_summary,
                },
            )
        session.commit()
        return KernelRelationClaimResponse.from_model(claim)
    except HTTPException:
        session.rollback()
        raise
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Claim write conflicts with graph integrity constraints",
        ) from exc
    except ValueError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except Exception as exc:  # noqa: BLE001
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create relation claim: {exc!s}",
        ) from exc


@router.get(
    "/{space_id}/claims/by-entity/{entity_id}",
    response_model=KernelRelationClaimListResponse,
    summary="List relation claims linked to one entity",
)
def list_claims_by_entity(
    space_id: UUID,
    entity_id: UUID,
    *,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    current_user: User = Depends(get_current_active_user),
    space_access: SpaceAccessPort = Depends(get_space_access_port),
    claim_participant_service: KernelClaimParticipantService = Depends(
        get_kernel_claim_participant_service,
    ),
    relation_claim_service: KernelRelationClaimService = Depends(
        get_kernel_relation_claim_service,
    ),
    session: Session = Depends(get_session),
) -> KernelRelationClaimListResponse:
    verify_space_membership(
        space_id=space_id,
        current_user=current_user,
        space_access=space_access,
        session=session,
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
        claims=[KernelRelationClaimResponse.from_model(claim) for claim in claims],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.get(
    "/{space_id}/claims/{claim_id}/participants",
    response_model=ClaimParticipantListResponse,
    summary="List structured participants for one claim",
)
def list_claim_participants(
    space_id: UUID,
    claim_id: UUID,
    *,
    current_user: User = Depends(get_current_active_user),
    space_access: SpaceAccessPort = Depends(get_space_access_port),
    claim_participant_service: KernelClaimParticipantService = Depends(
        get_kernel_claim_participant_service,
    ),
    relation_claim_service: KernelRelationClaimService = Depends(
        get_kernel_relation_claim_service,
    ),
    session: Session = Depends(get_session),
) -> ClaimParticipantListResponse:
    verify_space_membership(
        space_id=space_id,
        current_user=current_user,
        space_access=space_access,
        session=session,
    )
    claim = relation_claim_service.get_claim(str(claim_id))
    if claim is None or str(claim.research_space_id) != str(space_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
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


@router.get(
    "/{space_id}/claims/{claim_id}/evidence",
    response_model=KernelClaimEvidenceListResponse,
    summary="List evidence rows for one claim",
)
def list_claim_evidence(
    space_id: UUID,
    claim_id: UUID,
    *,
    current_user: User = Depends(get_current_active_user),
    space_access: SpaceAccessPort = Depends(get_space_access_port),
    relation_claim_service: KernelRelationClaimService = Depends(
        get_kernel_relation_claim_service,
    ),
    claim_evidence_service: KernelClaimEvidenceService = Depends(
        get_kernel_claim_evidence_service,
    ),
    session: Session = Depends(get_session),
) -> KernelClaimEvidenceListResponse:
    verify_space_membership(
        space_id=space_id,
        current_user=current_user,
        space_access=space_access,
        session=session,
    )
    claim = relation_claim_service.get_claim(str(claim_id))
    if claim is None or str(claim.research_space_id) != str(space_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Relation claim not found",
        )
    evidence_rows = claim_evidence_service.list_for_claim(str(claim_id))
    source_document_ids = {
        str(evidence_row.source_document_id)
        for evidence_row in evidence_rows
        if evidence_row.source_document_id is not None
    }
    source_documents_by_id: dict[str, SourceDocumentModel] = {}
    if source_document_ids:
        source_documents = session.scalars(
            select(SourceDocumentModel).where(
                SourceDocumentModel.id.in_(source_document_ids),
            ),
        ).all()
        source_documents_by_id = {
            str(source_document.id): source_document
            for source_document in source_documents
        }
    response_rows: list[KernelClaimEvidenceResponse] = []
    for evidence_row in evidence_rows:
        source_document = (
            source_documents_by_id.get(str(evidence_row.source_document_id))
            if evidence_row.source_document_id is not None
            else None
        )
        response_rows.append(
            KernelClaimEvidenceResponse.from_model(
                evidence_row,
                paper_links=resolve_claim_evidence_paper_links(
                    source_document=source_document,
                    evidence_metadata=evidence_row.metadata_payload,
                    source_document_ref=evidence_row.source_document_ref,
                ),
            ),
        )
    return KernelClaimEvidenceListResponse(
        claim_id=claim_id,
        evidence=response_rows,
        total=len(evidence_rows),
    )


@router.get(
    "/{space_id}/relations/conflicts",
    response_model=KernelRelationConflictListResponse,
    summary="List mixed-polarity canonical relation conflicts",
)
def list_relation_conflicts(
    space_id: UUID,
    *,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    current_user: User = Depends(get_current_active_user),
    space_access: SpaceAccessPort = Depends(get_space_access_port),
    relation_claim_service: KernelRelationClaimService = Depends(
        get_kernel_relation_claim_service,
    ),
    session: Session = Depends(get_session),
) -> KernelRelationConflictListResponse:
    verify_space_membership(
        space_id=space_id,
        current_user=current_user,
        space_access=space_access,
        session=session,
    )
    conflicts = relation_claim_service.list_conflicts_by_research_space(
        str(space_id),
        limit=limit,
        offset=offset,
    )
    if conflicts:
        increment_metric(
            "relations_conflict_detected_total",
            delta=len(conflicts),
            tags={"research_space_id": str(space_id)},
        )
    total = relation_claim_service.count_conflicts_by_research_space(str(space_id))
    return KernelRelationConflictListResponse(
        conflicts=[
            KernelRelationConflictResponse.from_model(conflict)
            for conflict in conflicts
        ],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.patch(
    "/{space_id}/claims/{claim_id}",
    response_model=KernelRelationClaimResponse,
    summary="Update relation-claim triage status",
)
def update_claim_status(  # noqa: PLR0915
    space_id: UUID,
    claim_id: UUID,
    request: KernelRelationClaimTriageRequest,
    current_user: User = Depends(get_current_active_user),
    space_access: SpaceAccessPort = Depends(get_space_access_port),
    relation_claim_service: KernelRelationClaimService = Depends(
        get_kernel_relation_claim_service,
    ),
    relation_projection_materialization_service: KernelRelationProjectionMaterializationService = Depends(
        get_kernel_relation_projection_materialization_service,
    ),
    reasoning_path_service: KernelReasoningPathService = Depends(
        get_kernel_reasoning_path_service,
    ),
    dictionary_service: DictionaryPort = Depends(get_dictionary_service),
    session: Session = Depends(get_session),
) -> KernelRelationClaimResponse:
    require_space_role(
        space_id=space_id,
        current_user=current_user,
        space_access=space_access,
        session=session,
        required_role=MembershipRole.CURATOR,
    )
    existing = relation_claim_service.get_claim(str(claim_id))
    if existing is None or str(existing.research_space_id) != str(space_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Relation claim not found",
        )
    try:
        normalized_status = _normalize_claim_status_filter(request.claim_status)
        if normalized_status is None:
            msg = "claim_status is required"
            raise ValueError(msg)
        updated = relation_claim_service.update_claim_status(
            str(claim_id),
            claim_status=normalized_status,
            triaged_by=str(current_user.id),
        )
        if normalized_status == "RESOLVED":
            if updated.persistability != "PERSISTABLE":
                msg = (
                    "Claim cannot be resolved yet because it is NON_PERSISTABLE. "
                    "Use Needs Mapping or Reject."
                )
                raise ValueError(msg)
            reviewed_by = str(current_user.id)
            _activate_dictionary_dependencies_for_claim(
                dictionary_service=dictionary_service,
                source_type=updated.source_type,
                relation_type=updated.relation_type,
                target_type=updated.target_type,
                reviewed_by=reviewed_by,
                source_ref=f"relation_claim:{updated.id}",
            )
            if updated.polarity == "SUPPORT":
                relation_projection = relation_projection_materialization_service.materialize_support_claim(
                    claim_id=str(updated.id),
                    research_space_id=str(space_id),
                    projection_origin="CLAIM_RESOLUTION",
                    reviewed_by=reviewed_by,
                )
                if relation_projection.relation is not None:
                    refreshed_claim = relation_claim_service.get_claim(str(updated.id))
                    if refreshed_claim is not None:
                        updated = refreshed_claim
            else:
                linked_relation = None
                try:
                    linked_relation = relation_projection_materialization_service.find_claim_backed_relation_for_claim(
                        claim_id=str(updated.id),
                        research_space_id=str(space_id),
                    )
                except ValueError:
                    linked_relation = None
                if linked_relation is not None:
                    updated = relation_claim_service.link_claim_to_relation(
                        str(updated.id),
                        linked_relation_id=str(linked_relation.id),
                    )
                else:
                    updated = relation_claim_service.clear_claim_relation_link(
                        str(updated.id),
                    )
        elif existing.polarity == "SUPPORT":
            relation_projection_materialization_service.detach_claim_projection(
                str(existing.id),
                str(space_id),
            )
        else:
            updated = relation_claim_service.clear_claim_relation_link(
                str(updated.id),
            )
        reasoning_path_service.mark_stale_for_claim_ids(
            [str(updated.id)],
            str(space_id),
        )
        session.commit()
        return KernelRelationClaimResponse.from_model(updated)
    except ValueError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except Exception as exc:  # noqa: BLE001
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update relation claim: {exc!s}",
        ) from exc


@router.get(
    "/{space_id}/claim-relations",
    response_model=ClaimRelationListResponse,
    summary="List claim-to-claim relation edges",
)
def list_claim_relations(
    space_id: UUID,
    *,
    relation_type: str | None = Query(default=None),
    review_status: str | None = Query(default=None),
    source_claim_id: UUID | None = Query(default=None),
    target_claim_id: UUID | None = Query(default=None),
    claim_id: UUID | None = Query(default=None),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    current_user: User = Depends(get_current_active_user),
    space_access: SpaceAccessPort = Depends(get_space_access_port),
    claim_relation_service: KernelClaimRelationService = Depends(
        get_kernel_claim_relation_service,
    ),
    session: Session = Depends(get_session),
) -> ClaimRelationListResponse:
    verify_space_membership(
        space_id=space_id,
        current_user=current_user,
        space_access=space_access,
        session=session,
    )
    try:
        normalized_relation_type = (
            normalize_claim_relation_type(relation_type)
            if relation_type is not None and relation_type.strip()
            else None
        )
        normalized_review_status = (
            normalize_review_status(review_status)
            if review_status is not None and review_status.strip()
            else None
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
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
            ClaimRelationResponse.from_model(relation) for relation in claim_relations
        ],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.post(
    "/{space_id}/claim-relations",
    response_model=ClaimRelationResponse,
    summary="Create one claim-to-claim relation edge",
)
def create_claim_relation(
    space_id: UUID,
    request: ClaimRelationCreateRequest,
    current_user: User = Depends(get_current_active_user),
    space_access: SpaceAccessPort = Depends(get_space_access_port),
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
    require_space_role(
        space_id=space_id,
        current_user=current_user,
        space_access=space_access,
        session=session,
        required_role=MembershipRole.RESEARCHER,
    )
    source_claim = relation_claim_service.get_claim(str(request.source_claim_id))
    target_claim = relation_claim_service.get_claim(str(request.target_claim_id))
    if source_claim is None or str(source_claim.research_space_id) != str(space_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Source claim not found",
        )
    if target_claim is None or str(target_claim.research_space_id) != str(space_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Target claim not found",
        )
    try:
        relation = claim_relation_service.create_claim_relation(
            research_space_id=str(space_id),
            source_claim_id=str(request.source_claim_id),
            target_claim_id=str(request.target_claim_id),
            relation_type=normalize_claim_relation_type(request.relation_type),
            agent_run_id=request.agent_run_id,
            source_document_id=(
                str(request.source_document_id)
                if request.source_document_id is not None
                else None
            ),
            source_document_ref=request.source_document_ref,
            confidence=request.confidence,
            review_status=normalize_review_status(request.review_status),
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
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except ClaimRelationConstraintError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Duplicate or invalid claim relation edge",
        ) from exc


@router.patch(
    "/{space_id}/claim-relations/{relation_id}",
    response_model=ClaimRelationResponse,
    summary="Update one claim relation review status",
)
def update_claim_relation_review_status(
    space_id: UUID,
    relation_id: UUID,
    request: ClaimRelationReviewUpdateRequest,
    current_user: User = Depends(get_current_active_user),
    space_access: SpaceAccessPort = Depends(get_space_access_port),
    claim_relation_service: KernelClaimRelationService = Depends(
        get_kernel_claim_relation_service,
    ),
    reasoning_path_service: KernelReasoningPathService = Depends(
        get_kernel_reasoning_path_service,
    ),
    session: Session = Depends(get_session),
) -> ClaimRelationResponse:
    require_space_role(
        space_id=space_id,
        current_user=current_user,
        space_access=space_access,
        session=session,
        required_role=MembershipRole.CURATOR,
    )
    existing = claim_relation_service.get_claim_relation(str(relation_id))
    if existing is None or str(existing.research_space_id) != str(space_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Claim relation not found",
        )
    try:
        updated = claim_relation_service.update_review_status(
            str(relation_id),
            review_status=normalize_review_status(request.review_status),
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
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


__all__ = [
    "create_claim_relation",
    "list_claim_evidence",
    "list_claim_participants",
    "list_claim_relations",
    "list_claims",
    "list_claims_by_entity",
    "list_relation_conflicts",
    "router",
    "update_claim_relation_review_status",
    "update_claim_status",
]
