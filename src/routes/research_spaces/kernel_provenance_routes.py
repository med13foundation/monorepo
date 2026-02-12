"""Kernel provenance endpoints scoped to research spaces."""

from __future__ import annotations

from uuid import UUID

from fastapi import Depends, HTTPException, Query
from sqlalchemy.orm import Session

from src.application.services.kernel.provenance_service import ProvenanceService
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
from src.routes.research_spaces.kernel_dependencies import get_provenance_service
from src.routes.research_spaces.kernel_schemas import (
    KernelProvenanceListResponse,
    KernelProvenanceResponse,
)

from .router import (
    HTTP_404_NOT_FOUND,
    research_spaces_router,
)


@research_spaces_router.get(
    "/{space_id}/provenance",
    response_model=KernelProvenanceListResponse,
    summary="List provenance records",
)
def list_kernel_provenance(
    space_id: UUID,
    *,
    source_type: str | None = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_active_user),
    membership_service: MembershipManagementService = Depends(get_membership_service),
    provenance_service: ProvenanceService = Depends(get_provenance_service),
    session: Session = Depends(get_session),
) -> KernelProvenanceListResponse:
    verify_space_membership(
        space_id,
        current_user.id,
        membership_service,
        session,
        current_user.role,
    )

    records = provenance_service.list_by_research_space(
        str(space_id),
        source_type=source_type,
        limit=limit,
        offset=offset,
    )
    return KernelProvenanceListResponse(
        provenance=[KernelProvenanceResponse.from_model(p) for p in records],
        total=len(records),
        offset=offset,
        limit=limit,
    )


@research_spaces_router.get(
    "/{space_id}/provenance/{provenance_id}",
    response_model=KernelProvenanceResponse,
    summary="Get provenance record",
)
def get_kernel_provenance(
    space_id: UUID,
    provenance_id: UUID,
    current_user: User = Depends(get_current_active_user),
    membership_service: MembershipManagementService = Depends(get_membership_service),
    provenance_service: ProvenanceService = Depends(get_provenance_service),
    session: Session = Depends(get_session),
) -> KernelProvenanceResponse:
    verify_space_membership(
        space_id,
        current_user.id,
        membership_service,
        session,
        current_user.role,
    )

    record = provenance_service.get_provenance(str(provenance_id))
    if record is None or str(record.research_space_id) != str(space_id):
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND,
            detail="Provenance record not found",
        )

    return KernelProvenanceResponse.from_model(record)
