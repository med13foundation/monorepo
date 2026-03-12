"""Unified graph document endpoints scoped to research spaces."""

from __future__ import annotations

from uuid import UUID

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from src.application.services.claim_first_metrics import (
    emit_graph_filter_preset_usage,
)
from src.application.services.kernel import (
    KernelClaimEvidenceService,
    KernelClaimParticipantService,
    KernelEntityService,
    KernelRelationClaimService,
    KernelRelationService,
)
from src.application.services.membership_management_service import (
    MembershipManagementService,
)
from src.database.session import get_session
from src.domain.entities.user import User
from src.routes.auth import get_current_active_user
from src.routes.research_spaces._kernel_graph_document_builder import (
    build_kernel_graph_document,
)
from src.routes.research_spaces.dependencies import (
    get_membership_service,
    verify_space_membership,
)
from src.routes.research_spaces.kernel_dependencies import (
    get_kernel_claim_evidence_service,
    get_kernel_claim_participant_service,
    get_kernel_entity_service,
    get_kernel_relation_claim_service,
    get_kernel_relation_service,
)
from src.routes.research_spaces.kernel_schemas import (
    KernelGraphDocumentRequest,
    KernelGraphDocumentResponse,
)

from .router import (
    HTTP_400_BAD_REQUEST,
    HTTP_404_NOT_FOUND,
    research_spaces_router,
)


@research_spaces_router.post(
    "/{space_id}/graph/document",
    response_model=KernelGraphDocumentResponse,
    summary="Build one unified graph document with canonical, claim, and evidence elements",
)
def get_kernel_graph_document(
    space_id: UUID,
    request: KernelGraphDocumentRequest,
    current_user: User = Depends(get_current_active_user),
    membership_service: MembershipManagementService = Depends(get_membership_service),
    entity_service: KernelEntityService = Depends(get_kernel_entity_service),
    relation_service: KernelRelationService = Depends(get_kernel_relation_service),
    relation_claim_service: KernelRelationClaimService = Depends(
        get_kernel_relation_claim_service,
    ),
    claim_participant_service: KernelClaimParticipantService = Depends(
        get_kernel_claim_participant_service,
    ),
    claim_evidence_service: KernelClaimEvidenceService = Depends(
        get_kernel_claim_evidence_service,
    ),
    session: Session = Depends(get_session),
) -> KernelGraphDocumentResponse:
    """Return a single graph document that already contains claim/evidence overlays."""
    verify_space_membership(
        space_id,
        current_user.id,
        membership_service,
        session,
        current_user.role,
    )
    emit_graph_filter_preset_usage(
        endpoint="graph_document",
        curation_statuses=request.curation_statuses,
    )

    if request.mode == "starter" and request.seed_entity_ids:
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail="seed_entity_ids must be empty when mode='starter'.",
        )
    if request.mode == "seeded" and not request.seed_entity_ids:
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail="seed_entity_ids is required when mode='seeded'.",
        )

    try:
        return build_kernel_graph_document(
            space_id=str(space_id),
            request=request,
            entity_service=entity_service,
            relation_service=relation_service,
            relation_claim_service=relation_claim_service,
            claim_participant_service=claim_participant_service,
            claim_evidence_service=claim_evidence_service,
            session=session,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


__all__ = ["get_kernel_graph_document"]
