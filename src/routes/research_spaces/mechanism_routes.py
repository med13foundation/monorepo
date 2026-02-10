"""Mechanism API routes scoped to research spaces."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.database.session import get_session
from src.domain.entities.user import User
from src.domain.value_objects import (
    EvidenceLevel,
    MechanismLifecycleState,
    ProteinDomain,
)
from src.infrastructure.dependency_injection.dependencies import (
    get_legacy_dependency_container,
)
from src.models.api import (
    MechanismCreate,
    MechanismResponse,
    MechanismUpdate,
    PaginatedResponse,
    ProteinDomainPayload,
)
from src.routes.auth import get_current_active_user
from src.routes.research_spaces.dependencies import (
    get_membership_service,
    require_curator_role,
    verify_space_membership,
)
from src.routes.serializers import serialize_mechanism
from src.type_definitions.common import MechanismUpdate as MechanismUpdatePayload

from .router import (
    HTTP_201_CREATED,
    HTTP_400_BAD_REQUEST,
    HTTP_404_NOT_FOUND,
    HTTP_500_INTERNAL_SERVER_ERROR,
    research_spaces_router,
)

if TYPE_CHECKING:
    from src.application.services import (
        MechanismApplicationService,
        MembershipManagementService,
    )


class MechanismListParams(BaseModel):
    page: int = Field(1, ge=1, description="Page number")
    per_page: int = Field(20, ge=1, le=100, description="Items per page")
    search: str | None = Field(None, description="Search by name/description")
    sort_by: str = Field("name", description="Sort field")
    sort_order: str = Field("asc", pattern="^(asc|desc)$", description="Sort order")

    model_config = {"extra": "ignore"}


def get_mechanism_service(
    db: Session = Depends(get_session),
) -> MechanismApplicationService:
    container = get_legacy_dependency_container()
    return container.create_mechanism_application_service(db)


def _payload_to_domains(
    payloads: list[ProteinDomainPayload],
) -> list[ProteinDomain]:
    return [ProteinDomain.model_validate(payload.model_dump()) for payload in payloads]


def _to_mechanism_update_payload(
    payload: MechanismUpdate,
) -> MechanismUpdatePayload:
    updates: MechanismUpdatePayload = {}
    if payload.name is not None:
        updates["name"] = payload.name
    if payload.description is not None:
        updates["description"] = payload.description
    if payload.evidence_tier is not None:
        updates["evidence_tier"] = payload.evidence_tier.value
    if payload.confidence_score is not None:
        updates["confidence_score"] = payload.confidence_score
    if payload.source is not None:
        updates["source"] = payload.source
    if payload.lifecycle_state is not None:
        updates["lifecycle_state"] = payload.lifecycle_state.value
    if payload.protein_domains is not None:
        updates["protein_domains"] = [
            domain.model_dump() for domain in payload.protein_domains
        ]
    if payload.phenotype_ids is not None:
        updates["phenotype_ids"] = payload.phenotype_ids
    return updates


def _require_space_membership(
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


@research_spaces_router.get(
    "/{space_id}/mechanisms",
    summary="List mechanisms in space",
    response_model=PaginatedResponse[MechanismResponse],
)
async def list_space_mechanisms(
    space_id: UUID,
    params: MechanismListParams = Depends(),
    current_user: User = Depends(get_current_active_user),
    membership_service: MembershipManagementService = Depends(get_membership_service),
    service: MechanismApplicationService = Depends(get_mechanism_service),
    session: Session = Depends(get_session),
) -> PaginatedResponse[MechanismResponse]:
    """Retrieve a paginated list of mechanisms for a research space."""
    _require_space_membership(space_id, current_user, membership_service, session)
    filters = {"research_space_id": str(space_id)}
    try:
        if params.search:
            mechanisms = service.search_mechanisms(
                params.search,
                limit=params.per_page,
                filters=filters,
            )
            total = len(mechanisms)
            page = 1
        else:
            mechanisms, total = service.list_mechanisms(
                page=params.page,
                per_page=params.per_page,
                sort_by=params.sort_by,
                sort_order=params.sort_order,
                filters=filters,
            )
            page = params.page

        responses = [serialize_mechanism(mech) for mech in mechanisms]
        total_pages = (total + params.per_page - 1) // params.per_page
        return PaginatedResponse(
            items=responses,
            total=total,
            page=page,
            per_page=params.per_page,
            total_pages=total_pages,
            has_next=page < total_pages,
            has_prev=page > 1,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve mechanisms: {exc!s}",
        ) from exc


@research_spaces_router.get(
    "/{space_id}/mechanisms/{mechanism_id}",
    summary="Get mechanism by ID",
    response_model=MechanismResponse,
)
async def get_space_mechanism(
    space_id: UUID,
    mechanism_id: int,
    current_user: User = Depends(get_current_active_user),
    membership_service: MembershipManagementService = Depends(get_membership_service),
    service: MechanismApplicationService = Depends(get_mechanism_service),
    session: Session = Depends(get_session),
) -> MechanismResponse:
    """Retrieve a mechanism by ID within a research space."""
    _require_space_membership(space_id, current_user, membership_service, session)
    try:
        mechanism = service.get_mechanism_by_id(mechanism_id)
        if not mechanism or mechanism.research_space_id != space_id:
            raise HTTPException(
                status_code=HTTP_404_NOT_FOUND,
                detail=f"Mechanism {mechanism_id} not found",
            )
        return serialize_mechanism(mechanism)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve mechanism: {exc!s}",
        ) from exc


@research_spaces_router.post(
    "/{space_id}/mechanisms",
    summary="Create mechanism",
    response_model=MechanismResponse,
    status_code=HTTP_201_CREATED,
)
async def create_space_mechanism(
    space_id: UUID,
    payload: MechanismCreate,
    current_user: User = Depends(get_current_active_user),
    membership_service: MembershipManagementService = Depends(get_membership_service),
    service: MechanismApplicationService = Depends(get_mechanism_service),
    session: Session = Depends(get_session),
) -> MechanismResponse:
    """Create a new mechanism within a research space."""
    require_curator_role(
        space_id,
        current_user.id,
        membership_service,
        session,
        current_user.role,
    )
    try:
        protein_domains = _payload_to_domains(payload.protein_domains)
        mechanism = service.create_mechanism(
            name=payload.name,
            research_space_id=space_id,
            description=payload.description,
            evidence_tier=EvidenceLevel(payload.evidence_tier.value),
            confidence_score=payload.confidence_score,
            source=payload.source,
            lifecycle_state=MechanismLifecycleState(payload.lifecycle_state.value),
            protein_domains=protein_domains,
            phenotype_ids=payload.phenotype_ids,
        )
        return serialize_mechanism(mechanism)
    except Exception as exc:
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail=f"Failed to create mechanism: {exc!s}",
        ) from exc


@research_spaces_router.put(
    "/{space_id}/mechanisms/{mechanism_id}",
    summary="Update mechanism",
    response_model=MechanismResponse,
)
async def update_space_mechanism(
    space_id: UUID,
    mechanism_id: int,
    payload: MechanismUpdate,
    current_user: User = Depends(get_current_active_user),
    membership_service: MembershipManagementService = Depends(get_membership_service),
    service: MechanismApplicationService = Depends(get_mechanism_service),
    session: Session = Depends(get_session),
) -> MechanismResponse:
    """Update an existing mechanism within a research space."""
    require_curator_role(
        space_id,
        current_user.id,
        membership_service,
        session,
        current_user.role,
    )
    try:
        existing = service.get_mechanism_by_id(mechanism_id)
        if not existing or existing.research_space_id != space_id:
            raise HTTPException(
                status_code=HTTP_404_NOT_FOUND,
                detail=f"Mechanism {mechanism_id} not found",
            )
        updates = _to_mechanism_update_payload(payload)
        mechanism = service.update_mechanism(mechanism_id, updates)
        return serialize_mechanism(mechanism)
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update mechanism: {exc!s}",
        ) from exc


@research_spaces_router.delete(
    "/{space_id}/mechanisms/{mechanism_id}",
    summary="Delete mechanism",
)
async def delete_space_mechanism(
    space_id: UUID,
    mechanism_id: int,
    current_user: User = Depends(get_current_active_user),
    membership_service: MembershipManagementService = Depends(get_membership_service),
    service: MechanismApplicationService = Depends(get_mechanism_service),
    session: Session = Depends(get_session),
) -> dict[str, str]:
    """Delete a mechanism by ID within a research space."""
    require_curator_role(
        space_id,
        current_user.id,
        membership_service,
        session,
        current_user.role,
    )
    try:
        existing = service.get_mechanism_by_id(mechanism_id)
        if not existing or existing.research_space_id != space_id:
            raise HTTPException(
                status_code=HTTP_404_NOT_FOUND,
                detail=f"Mechanism {mechanism_id} not found",
            )
        deleted = service.delete_mechanism(mechanism_id)
        if not deleted:
            raise HTTPException(
                status_code=HTTP_404_NOT_FOUND,
                detail=f"Mechanism {mechanism_id} not found",
            )
        return {"message": "Mechanism deleted"}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete mechanism: {exc!s}",
        ) from exc


__all__ = ["research_spaces_router"]
