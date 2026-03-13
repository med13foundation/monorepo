"""Provenance routes for the standalone graph service."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from services.graph_api.auth import get_current_active_user
from services.graph_api.database import get_session
from services.graph_api.dependencies import (
    get_provenance_service,
    get_space_access_port,
    verify_space_membership,
)
from src.application.services.kernel.provenance_service import ProvenanceService
from src.domain.entities.user import User
from src.domain.ports.space_access_port import SpaceAccessPort
from src.type_definitions.graph_service_contracts import (
    KernelProvenanceListResponse,
    KernelProvenanceResponse,
)

router = APIRouter(prefix="/v1/spaces", tags=["provenance"])


@router.get(
    "/{space_id}/provenance",
    response_model=KernelProvenanceListResponse,
    summary="List provenance records",
)
def list_provenance(
    space_id: UUID,
    *,
    source_type: str | None = Query(default=None),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    current_user: User = Depends(get_current_active_user),
    space_access: SpaceAccessPort = Depends(get_space_access_port),
    provenance_service: ProvenanceService = Depends(get_provenance_service),
    session: Session = Depends(get_session),
) -> KernelProvenanceListResponse:
    """List provenance records in one graph space."""
    verify_space_membership(
        space_id=space_id,
        current_user=current_user,
        space_access=space_access,
        session=session,
    )

    records = provenance_service.list_by_research_space(
        str(space_id),
        source_type=source_type,
        limit=limit,
        offset=offset,
    )
    return KernelProvenanceListResponse(
        provenance=[KernelProvenanceResponse.from_model(record) for record in records],
        total=len(records),
        offset=offset,
        limit=limit,
    )


@router.get(
    "/{space_id}/provenance/{provenance_id}",
    response_model=KernelProvenanceResponse,
    summary="Get one provenance record",
)
def get_provenance(
    space_id: UUID,
    provenance_id: UUID,
    *,
    current_user: User = Depends(get_current_active_user),
    space_access: SpaceAccessPort = Depends(get_space_access_port),
    provenance_service: ProvenanceService = Depends(get_provenance_service),
    session: Session = Depends(get_session),
) -> KernelProvenanceResponse:
    """Fetch one provenance record in one graph space."""
    verify_space_membership(
        space_id=space_id,
        current_user=current_user,
        space_access=space_access,
        session=session,
    )

    record = provenance_service.get_provenance(str(provenance_id))
    if record is None or str(record.research_space_id) != str(space_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Provenance record not found",
        )

    return KernelProvenanceResponse.from_model(record)


__all__ = ["get_provenance", "list_provenance", "router"]
