"""Admin Artana run explorer routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from src.application.services.artana_observability_service import (
    ArtanaObservabilityService,
)
from src.application.services.authorization_service import (
    AuthorizationError,
    AuthorizationService,
)
from src.domain.entities.user import User
from src.domain.value_objects.permission import Permission
from src.infrastructure.dependency_injection.container import container
from src.infrastructure.llm.state import SqlAlchemyAgentRunStateRepository
from src.routes.artana_observability_dependencies import get_artana_run_trace_port
from src.routes.auth import get_current_active_user
from src.routes.research_spaces.artana_run_schemas import (
    ArtanaRunListResponse,
    ArtanaRunTraceResponse,
)

from .artana_runs_schemas import ArtanaRunListQueryParams
from .dependencies import get_admin_db_session

router = APIRouter(tags=["artana"])


async def _require_permission(
    *,
    permission: Permission,
    current_user: User,
    authz_service: AuthorizationService,
) -> None:
    try:
        await authz_service.require_permission(current_user.id, permission)
    except AuthorizationError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc


def _build_observability_service(session: Session) -> ArtanaObservabilityService:
    return ArtanaObservabilityService(
        session=session,
        run_trace=get_artana_run_trace_port(),
        raw_state=SqlAlchemyAgentRunStateRepository(session),
    )


def get_admin_artana_observability_service(
    session: Annotated[Session, Depends(get_admin_db_session)],
) -> ArtanaObservabilityService:
    """Provide the admin Artana observability service."""
    return _build_observability_service(session)


@router.get(
    "/artana/runs",
    response_model=ArtanaRunListResponse,
    summary="List Artana runs for developer observability",
)
async def list_artana_runs(
    query: Annotated[ArtanaRunListQueryParams, Depends()],
    current_user: Annotated[User, Depends(get_current_active_user)],
    authz_service: Annotated[
        AuthorizationService,
        Depends(container.get_authorization_service),
    ],
    observability_service: Annotated[
        ArtanaObservabilityService,
        Depends(get_admin_artana_observability_service),
    ],
) -> ArtanaRunListResponse:
    await _require_permission(
        permission=Permission.SYSTEM_ADMIN,
        current_user=current_user,
        authz_service=authz_service,
    )
    payload = observability_service.list_admin_runs(
        q=query.q,
        status=query.status,
        space_id=query.space_id,
        source_type=query.source_type,
        alert_code=query.alert_code,
        since_hours=query.since_hours,
        page=query.page,
        per_page=query.per_page,
    )
    return ArtanaRunListResponse.model_validate(payload)


@router.get(
    "/artana/runs/{run_id}",
    response_model=ArtanaRunTraceResponse,
    summary="Get Artana run observability detail",
)
async def get_artana_run_trace(
    run_id: str,
    current_user: Annotated[User, Depends(get_current_active_user)],
    authz_service: Annotated[
        AuthorizationService,
        Depends(container.get_authorization_service),
    ],
    observability_service: Annotated[
        ArtanaObservabilityService,
        Depends(get_admin_artana_observability_service),
    ],
) -> ArtanaRunTraceResponse:
    await _require_permission(
        permission=Permission.SYSTEM_ADMIN,
        current_user=current_user,
        authz_service=authz_service,
    )
    try:
        payload = observability_service.get_admin_run_trace(run_id=run_id)
        return ArtanaRunTraceResponse.model_validate(payload)
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except Exception as exc:  # pragma: no cover - defensive guard
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to load Artana run trace: {exc!s}",
        ) from exc


__all__ = ["get_admin_artana_observability_service", "router"]
