"""Read routes for derived reasoning paths."""

from __future__ import annotations

from uuid import UUID

from fastapi import Depends, HTTPException, Query
from sqlalchemy.orm import Session

from src.application.services.kernel import KernelReasoningPathService
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
    get_kernel_reasoning_path_service,
)
from src.routes.research_spaces.kernel_reasoning_path_schemas import (
    KernelReasoningPathDetailResponse,
    KernelReasoningPathListResponse,
    KernelReasoningPathResponse,
)

from .router import HTTP_404_NOT_FOUND, research_spaces_router


@research_spaces_router.get(
    "/{space_id}/graph/reasoning-paths",
    response_model=KernelReasoningPathListResponse,
    summary="List derived reasoning paths in a research space",
)
def list_reasoning_paths(
    space_id: UUID,
    *,
    start_entity_id: UUID | None = Query(default=None),
    end_entity_id: UUID | None = Query(default=None),
    status: str | None = Query(default=None, pattern="^(ACTIVE|STALE)$"),
    path_kind: str | None = Query(default=None, pattern="^(MECHANISM)$"),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    current_user: User = Depends(get_current_active_user),
    membership_service: MembershipManagementService = Depends(get_membership_service),
    reasoning_path_service: KernelReasoningPathService = Depends(
        get_kernel_reasoning_path_service,
    ),
    session: Session = Depends(get_session),
) -> KernelReasoningPathListResponse:
    verify_space_membership(
        space_id,
        current_user.id,
        membership_service,
        session,
        current_user.role,
    )
    result = reasoning_path_service.list_paths(
        research_space_id=str(space_id),
        start_entity_id=str(start_entity_id) if start_entity_id is not None else None,
        end_entity_id=str(end_entity_id) if end_entity_id is not None else None,
        status=status,  # type: ignore[arg-type]
        path_kind=path_kind,  # type: ignore[arg-type]
        limit=limit,
        offset=offset,
    )
    return KernelReasoningPathListResponse(
        paths=[KernelReasoningPathResponse.from_model(path) for path in result.paths],
        total=result.total,
        offset=result.offset,
        limit=result.limit,
    )


@research_spaces_router.get(
    "/{space_id}/graph/reasoning-paths/{path_id}",
    response_model=KernelReasoningPathDetailResponse,
    summary="Retrieve one fully explained reasoning path",
)
def get_reasoning_path(
    space_id: UUID,
    path_id: UUID,
    *,
    current_user: User = Depends(get_current_active_user),
    membership_service: MembershipManagementService = Depends(get_membership_service),
    reasoning_path_service: KernelReasoningPathService = Depends(
        get_kernel_reasoning_path_service,
    ),
    session: Session = Depends(get_session),
) -> KernelReasoningPathDetailResponse:
    verify_space_membership(
        space_id,
        current_user.id,
        membership_service,
        session,
        current_user.role,
    )
    detail = reasoning_path_service.get_path(str(path_id), str(space_id))
    if detail is None:
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND,
            detail=f"Reasoning path {path_id} not found",
        )
    return KernelReasoningPathDetailResponse.from_detail(detail)


__all__ = ["get_reasoning_path", "list_reasoning_paths"]
