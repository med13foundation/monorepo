"""Unified graph document endpoints scoped to research spaces."""

from __future__ import annotations

from uuid import UUID

from fastapi import Depends, HTTPException

from src.application.services.claim_first_metrics import (
    emit_graph_filter_preset_usage,
)
from src.domain.entities.user import User
from src.routes.auth import get_current_active_user
from src.routes.research_spaces._kernel_graph_document_builder import (
    build_kernel_graph_document,
)
from src.routes.research_spaces._kernel_graph_document_dependencies import (
    KernelGraphDocumentDependencies,
    get_kernel_graph_document_dependencies,
)
from src.routes.research_spaces.dependencies import (
    verify_space_membership,
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
    dependencies: KernelGraphDocumentDependencies = Depends(
        get_kernel_graph_document_dependencies,
    ),
) -> KernelGraphDocumentResponse:
    """Return a single graph document that already contains claim/evidence overlays."""
    verify_space_membership(
        space_id,
        current_user.id,
        dependencies.membership_service,
        dependencies.session,
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
            entity_service=dependencies.entity_service,
            relation_service=dependencies.relation_service,
            relation_claim_service=dependencies.relation_claim_service,
            relation_projection_source_service=(
                dependencies.relation_projection_source_service
            ),
            claim_participant_service=dependencies.claim_participant_service,
            claim_evidence_service=dependencies.claim_evidence_service,
            session=dependencies.session,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


__all__ = ["get_kernel_graph_document"]
