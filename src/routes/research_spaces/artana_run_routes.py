"""Artana observability routes scoped to one research space."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from src.application.services.artana_observability_service import (
    ArtanaObservabilityService,
)
from src.application.services.membership_management_service import (
    MembershipManagementService,
)
from src.database.session import get_session
from src.domain.entities.user import User
from src.infrastructure.llm.state import SqlAlchemyAgentRunStateRepository
from src.routes.artana_observability_dependencies import get_artana_run_trace_port
from src.routes.auth import get_current_active_user
from src.routes.research_spaces.dependencies import (
    get_membership_service,
    verify_space_membership,
)

from .artana_run_schemas import ArtanaRunTraceResponse
from .router import (
    HTTP_404_NOT_FOUND,
    HTTP_500_INTERNAL_SERVER_ERROR,
    research_spaces_router,
)


def get_artana_observability_service(
    session: Annotated[Session, Depends(get_session)],
) -> ArtanaObservabilityService:
    """Provide the shared observability read model service."""
    return ArtanaObservabilityService(
        session=session,
        run_trace=get_artana_run_trace_port(),
        raw_state=SqlAlchemyAgentRunStateRepository(session),
    )


@research_spaces_router.get(
    "/{space_id}/artana-runs/{run_id}",
    response_model=ArtanaRunTraceResponse,
    summary="Get Artana observability detail for one run or pipeline run",
)
def get_space_artana_run_trace(
    space_id: UUID,
    run_id: str,
    current_user: Annotated[User, Depends(get_current_active_user)],
    membership_service: Annotated[
        MembershipManagementService,
        Depends(get_membership_service),
    ],
    observability_service: Annotated[
        ArtanaObservabilityService,
        Depends(get_artana_observability_service),
    ],
    session: Annotated[Session, Depends(get_session)],
) -> ArtanaRunTraceResponse:
    verify_space_membership(
        space_id,
        current_user.id,
        membership_service,
        session,
        current_user.role,
    )
    try:
        payload = observability_service.get_space_run_trace(
            space_id=space_id,
            run_id=run_id,
        )
        return ArtanaRunTraceResponse.model_validate(payload)
    except LookupError as exc:
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except Exception as exc:  # pragma: no cover - defensive guard
        raise HTTPException(
            status_code=HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to load Artana run trace: {exc!s}",
        ) from exc


__all__ = ["get_artana_observability_service"]
