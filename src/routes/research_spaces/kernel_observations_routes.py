"""Kernel observation endpoints scoped to research spaces."""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from fastapi import Depends, HTTPException, Query
from sqlalchemy.orm import Session

from src.application.services.kernel.dictionary_service import DictionaryService
from src.application.services.kernel.kernel_entity_service import KernelEntityService
from src.application.services.kernel.kernel_observation_service import (
    KernelObservationService,
)
from src.application.services.membership_management_service import (
    MembershipManagementService,
)
from src.database.session import get_session
from src.domain.entities.user import User
from src.routes.auth import get_current_active_user
from src.routes.research_spaces.dependencies import (
    get_membership_service,
    require_researcher_role,
    verify_space_membership,
)
from src.routes.research_spaces.kernel_dependencies import (
    get_dictionary_service,
    get_kernel_entity_service,
    get_kernel_observation_service,
)
from src.routes.research_spaces.kernel_schemas import (
    KernelObservationCreateRequest,
    KernelObservationListResponse,
    KernelObservationResponse,
)
from src.type_definitions.common import JSONValue

from .router import (
    HTTP_201_CREATED,
    HTTP_400_BAD_REQUEST,
    HTTP_404_NOT_FOUND,
    HTTP_500_INTERNAL_SERVER_ERROR,
    research_spaces_router,
)


def _parse_iso_date_value(raw: str) -> datetime | date:
    """
    Parse an ISO date or datetime string.

    Accepts:
    - YYYY-MM-DD
    - full datetime (with optional timezone)
    - trailing 'Z' (converted to +00:00)
    """
    raw_norm = raw.strip()
    if raw_norm.endswith("Z"):
        raw_norm = f"{raw_norm[:-1]}+00:00"

    try:
        return datetime.fromisoformat(raw_norm)
    except ValueError:
        return date.fromisoformat(raw_norm)


@research_spaces_router.post(
    "/{space_id}/observations",
    response_model=KernelObservationResponse,
    summary="Record a kernel observation",
    status_code=HTTP_201_CREATED,
)
def create_kernel_observation(
    space_id: UUID,
    request: KernelObservationCreateRequest,
    current_user: User = Depends(get_current_active_user),
    membership_service: MembershipManagementService = Depends(get_membership_service),
    dictionary_service: DictionaryService = Depends(get_dictionary_service),
    observation_service: KernelObservationService = Depends(
        get_kernel_observation_service,
    ),
    session: Session = Depends(get_session),
) -> KernelObservationResponse:
    require_researcher_role(
        space_id,
        current_user.id,
        membership_service,
        session,
        current_user.role,
    )

    variable = dictionary_service.get_variable(request.variable_id)
    if variable is None:
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail=f"Unknown variable_id: {request.variable_id}",
        )

    value_to_record: JSONValue | datetime | date
    if variable.data_type in ("DATE", "DATETIME"):
        if not isinstance(request.value, str):
            raise HTTPException(
                status_code=HTTP_400_BAD_REQUEST,
                detail="DATE variables require an ISO date/datetime string value.",
            )
        try:
            value_to_record = _parse_iso_date_value(request.value)
        except ValueError as e:
            raise HTTPException(
                status_code=HTTP_400_BAD_REQUEST,
                detail=f"Invalid ISO date/datetime value: {request.value}",
            ) from e
    else:
        value_to_record = request.value

    try:
        obs = observation_service.record_observation_value(
            research_space_id=str(space_id),
            subject_id=str(request.subject_id),
            variable_id=request.variable_id,
            value=value_to_record,
            unit=request.unit,
            observed_at=request.observed_at,
            provenance_id=str(request.provenance_id) if request.provenance_id else None,
            confidence=request.confidence,
        )
        session.commit()
        return KernelObservationResponse.from_model(obs)
    except ValueError as e:
        session.rollback()
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e
    except Exception as e:
        session.rollback()
        raise HTTPException(
            status_code=HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to record observation: {e!s}",
        ) from e


@research_spaces_router.get(
    "/{space_id}/observations",
    response_model=KernelObservationListResponse,
    summary="List kernel observations",
)
def list_kernel_observations(
    space_id: UUID,
    *,
    subject_id: UUID | None = Query(
        None,
        description="Filter by subject entity_id",
    ),
    variable_id: str | None = Query(None, description="Filter by variable_id"),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_active_user),
    membership_service: MembershipManagementService = Depends(get_membership_service),
    entity_service: KernelEntityService = Depends(get_kernel_entity_service),
    observation_service: KernelObservationService = Depends(
        get_kernel_observation_service,
    ),
    session: Session = Depends(get_session),
) -> KernelObservationListResponse:
    verify_space_membership(
        space_id,
        current_user.id,
        membership_service,
        session,
        current_user.role,
    )

    if subject_id is not None:
        subject = entity_service.get_entity(str(subject_id))
        if subject is None or str(subject.research_space_id) != str(space_id):
            raise HTTPException(
                status_code=HTTP_404_NOT_FOUND,
                detail="Subject entity not found",
            )
        observations = observation_service.get_subject_observations(
            str(subject_id),
            variable_id=variable_id,
            limit=limit,
            offset=offset,
        )
    else:
        observations = observation_service.get_research_space_observations(
            str(space_id),
            limit=limit,
            offset=offset,
        )

    return KernelObservationListResponse(
        observations=[KernelObservationResponse.from_model(o) for o in observations],
        total=len(observations),
        offset=offset,
        limit=limit,
    )


@research_spaces_router.get(
    "/{space_id}/observations/{observation_id}",
    response_model=KernelObservationResponse,
    summary="Get kernel observation",
)
def get_kernel_observation(
    space_id: UUID,
    observation_id: UUID,
    current_user: User = Depends(get_current_active_user),
    membership_service: MembershipManagementService = Depends(get_membership_service),
    observation_service: KernelObservationService = Depends(
        get_kernel_observation_service,
    ),
    session: Session = Depends(get_session),
) -> KernelObservationResponse:
    verify_space_membership(
        space_id,
        current_user.id,
        membership_service,
        session,
        current_user.role,
    )

    obs = observation_service.get_observation(str(observation_id))
    if obs is None or str(obs.research_space_id) != str(space_id):
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND,
            detail="Observation not found",
        )

    return KernelObservationResponse.from_model(obs)
