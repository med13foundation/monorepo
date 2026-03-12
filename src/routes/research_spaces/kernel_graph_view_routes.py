"""Read-side graph view routes for domain views and mechanism chains."""

from __future__ import annotations

from uuid import UUID

from fastapi import Depends, HTTPException, Query
from sqlalchemy.orm import Session

from src.application.services.kernel.kernel_graph_view_service import (
    GraphDomainViewType,
    KernelGraphViewNotFoundError,
    KernelGraphViewService,
    KernelGraphViewValidationError,
)
from src.application.services.membership_management_service import (
    MembershipManagementService,
)
from src.database.session import get_session
from src.domain.entities.user import User
from src.routes.auth import get_current_active_user
from src.routes.research_spaces.dependencies import (
    get_membership_service,
    verify_space_membership,
)
from src.routes.research_spaces.kernel_dependencies import (
    get_kernel_graph_view_service,
)
from src.routes.research_spaces.kernel_graph_view_schemas import (
    KernelClaimMechanismChainResponse,
    KernelGraphDomainViewResponse,
)

from .router import (
    HTTP_400_BAD_REQUEST,
    HTTP_404_NOT_FOUND,
    research_spaces_router,
)


def _normalize_view_type(value: str) -> GraphDomainViewType:
    normalized = value.strip().lower()
    if normalized == "gene":
        return "gene"
    if normalized == "variant":
        return "variant"
    if normalized == "phenotype":
        return "phenotype"
    if normalized == "paper":
        return "paper"
    if normalized == "claim":
        return "claim"
    msg = f"Unsupported graph view type '{value}'"
    raise ValueError(msg)


@research_spaces_router.get(
    "/{space_id}/graph/views/{view_type}/{resource_id}",
    response_model=KernelGraphDomainViewResponse,
    summary="Build one claim-aware domain view",
)
def get_graph_domain_view(
    space_id: UUID,
    view_type: str,
    resource_id: UUID,
    *,
    claim_limit: int = Query(50, ge=1, le=200),
    relation_limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_active_user),
    membership_service: MembershipManagementService = Depends(get_membership_service),
    graph_view_service: KernelGraphViewService = Depends(get_kernel_graph_view_service),
    session: Session = Depends(get_session),
) -> KernelGraphDomainViewResponse:
    verify_space_membership(
        space_id,
        current_user.id,
        membership_service,
        session,
        current_user.role,
    )
    try:
        normalized_view_type = _normalize_view_type(view_type)
        domain_view = graph_view_service.build_domain_view(
            research_space_id=str(space_id),
            view_type=normalized_view_type,
            resource_id=str(resource_id),
            claim_limit=claim_limit,
            relation_limit=relation_limit,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except KernelGraphViewValidationError as exc:
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except KernelGraphViewNotFoundError as exc:
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    return KernelGraphDomainViewResponse.from_domain_view(domain_view)


@research_spaces_router.get(
    "/{space_id}/claims/{claim_id}/mechanism-chain",
    response_model=KernelClaimMechanismChainResponse,
    summary="Traverse a mechanism-style claim chain from one root claim",
)
def get_claim_mechanism_chain(
    space_id: UUID,
    claim_id: UUID,
    *,
    max_depth: int = Query(3, ge=1, le=6),
    current_user: User = Depends(get_current_active_user),
    membership_service: MembershipManagementService = Depends(get_membership_service),
    graph_view_service: KernelGraphViewService = Depends(get_kernel_graph_view_service),
    session: Session = Depends(get_session),
) -> KernelClaimMechanismChainResponse:
    verify_space_membership(
        space_id,
        current_user.id,
        membership_service,
        session,
        current_user.role,
    )
    try:
        chain = graph_view_service.build_mechanism_chain(
            research_space_id=str(space_id),
            claim_id=str(claim_id),
            max_depth=max_depth,
        )
    except KernelGraphViewValidationError as exc:
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except KernelGraphViewNotFoundError as exc:
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    return KernelClaimMechanismChainResponse.from_chain(chain)


__all__ = ["get_claim_mechanism_chain", "get_graph_domain_view"]
