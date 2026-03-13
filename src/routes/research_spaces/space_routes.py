"""Research space CRUD route handlers."""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from src.application.curation.services.review_service import ReviewQuery, ReviewService
from src.application.services import (
    membership_management_service,
    research_space_management_service,
)
from src.database.session import get_session
from src.domain.entities import (
    research_space,
    research_space_membership,
    user,
)
from src.infrastructure.graph_service.errors import GraphServiceClientError
from src.infrastructure.repositories.user_data_source_repository import (
    SqlAlchemyUserDataSourceRepository,
)
from src.routes.auth import get_current_active_user
from src.routes.research_spaces.dependencies import (
    get_curation_service,
    get_membership_service,
    get_research_space_service,
    verify_space_membership,
)
from src.routes.research_spaces.schemas import (
    CreateSpaceRequestModel,
    CurationQueueItemResponse,
    CurationQueueResponse,
    CurationStatsResponse,
    DataSourceResponse,
    MembershipResponse,
    ResearchSpaceListResponse,
    ResearchSpaceResponse,
    SpaceOverviewAccessResponse,
    SpaceOverviewCountsResponse,
    SpaceOverviewDataSourcesResponse,
    SpaceOverviewResponse,
    UpdateSpaceRequestModel,
)

from .router import (
    HTTP_201_CREATED,
    HTTP_400_BAD_REQUEST,
    HTTP_404_NOT_FOUND,
    HTTP_500_INTERNAL_SERVER_ERROR,
    research_spaces_router,
)

logger = logging.getLogger(__name__)


def _build_admin_membership_response(
    space_id: UUID,
    current_user: user.User,
) -> MembershipResponse:
    """Return synthetic membership for platform admins."""
    return MembershipResponse(
        id=UUID(int=0),
        space_id=space_id,
        user_id=current_user.id,
        role=research_space_membership.MembershipRole.ADMIN.value,
        invited_by=None,
        invited_at=None,
        joined_at=None,
        is_active=True,
        created_at=current_user.created_at.isoformat(),
        updated_at=current_user.updated_at.isoformat(),
    )


def _can_manage_members(
    *,
    role: research_space_membership.MembershipRole,
    is_platform_admin: bool,
) -> bool:
    """Role check for membership-management capabilities."""
    return is_platform_admin or role in {
        research_space_membership.MembershipRole.OWNER,
        research_space_membership.MembershipRole.ADMIN,
    }


def get_space_overview_limits(
    data_source_limit: int = Query(5, ge=1, le=50),
    queue_limit: int = Query(5, ge=1, le=50),
) -> tuple[int, int]:
    """Dependency wrapper for overview preview limits."""
    return data_source_limit, queue_limit


@research_spaces_router.post(
    "",
    response_model=ResearchSpaceResponse,
    summary="Create research space",
    description="Create a new research space",
    status_code=HTTP_201_CREATED,
)
def create_space(
    request: CreateSpaceRequestModel,
    current_user: user.User = Depends(get_current_active_user),
    service: research_space_management_service.ResearchSpaceManagementService = Depends(
        get_research_space_service,
    ),
) -> ResearchSpaceResponse:
    """Create a new research space."""
    try:
        create_request = research_space_management_service.CreateSpaceRequest(
            owner_id=current_user.id,
            name=request.name,
            slug=request.slug,
            description=request.description,
            settings=request.settings,
            tags=request.tags,
        )
        try:
            space = service.create_space(create_request)
        except GraphServiceClientError as exc:
            raise HTTPException(
                status_code=HTTP_500_INTERNAL_SERVER_ERROR,
                detail=(
                    "Research space was created but graph-space sync failed: "
                    + (exc.detail or str(exc))
                ),
            ) from exc
        return ResearchSpaceResponse.from_entity(space)
    except ValueError as e:
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e


@research_spaces_router.get(
    "",
    response_model=ResearchSpaceListResponse,
    summary="List research spaces",
    description="Get paginated list of research spaces",
)
def list_spaces(
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(50, ge=1, le=100, description="Maximum number of records"),
    owner_id: UUID | None = Query(None, description="Filter by owner"),
    current_user: user.User = Depends(get_current_active_user),
    service: research_space_management_service.ResearchSpaceManagementService = Depends(
        get_research_space_service,
    ),
) -> ResearchSpaceListResponse:
    """List research spaces with pagination."""
    try:
        if owner_id:
            spaces = service.get_user_spaces(owner_id, skip, limit)
        else:
            spaces = service.get_active_spaces(skip, limit)

        return ResearchSpaceListResponse(
            spaces=[ResearchSpaceResponse.from_entity(space) for space in spaces],
            total=len(spaces),
            skip=skip,
            limit=limit,
        )
    except Exception as e:
        raise HTTPException(
            status_code=HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list spaces: {e!s}",
        ) from e


@research_spaces_router.get(
    "/{space_id}",
    response_model=ResearchSpaceResponse,
    summary="Get research space",
    description="Get a research space by ID",
)
def get_space(
    space_id: UUID,
    current_user: user.User = Depends(get_current_active_user),
    service: research_space_management_service.ResearchSpaceManagementService = Depends(
        get_research_space_service,
    ),
) -> ResearchSpaceResponse:
    """Get a research space by ID."""
    space = service.get_space(space_id, current_user.id)
    if not space:
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND,
            detail=f"Research space {space_id} not found",
        )
    return ResearchSpaceResponse.from_entity(space)


@research_spaces_router.get(
    "/{space_id}/overview",
    response_model=SpaceOverviewResponse,
    summary="Get research space overview",
    description=(
        "Get a consolidated overview payload with access flags, curation stats, "
        "and data source preview for dashboard rendering."
    ),
)
def get_space_overview(
    space_id: UUID,
    limits: tuple[int, int] = Depends(get_space_overview_limits),
    current_user: user.User = Depends(get_current_active_user),
    space_service: research_space_management_service.ResearchSpaceManagementService = Depends(
        get_research_space_service,
    ),
    membership_service: membership_management_service.MembershipManagementService = Depends(
        get_membership_service,
    ),
    curation_service: ReviewService = Depends(get_curation_service),
    session: Session = Depends(get_session),
) -> SpaceOverviewResponse:
    """Return space overview data used by the dashboard page."""
    data_source_limit, queue_limit = limits

    verify_space_membership(
        space_id,
        current_user.id,
        membership_service,
        session,
        current_user.role,
    )

    space = space_service.get_space(space_id, current_user.id)
    if not space:
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND,
            detail=f"Research space {space_id} not found",
        )

    is_platform_admin = current_user.role == user.UserRole.ADMIN
    membership = membership_service.get_membership_for_user(space_id, current_user.id)

    membership_response: MembershipResponse | None
    effective_role: research_space_membership.MembershipRole
    if membership is not None:
        membership_response = MembershipResponse.from_entity(membership)
        effective_role = membership.role
    elif is_platform_admin:
        membership_response = _build_admin_membership_response(space_id, current_user)
        effective_role = research_space_membership.MembershipRole.ADMIN
    else:
        membership_response = None
        effective_role = research_space_membership.MembershipRole.VIEWER

    has_space_access = is_platform_admin or membership is not None
    is_owner = effective_role == research_space_membership.MembershipRole.OWNER
    can_manage_members = _can_manage_members(
        role=effective_role,
        is_platform_admin=is_platform_admin,
    )
    can_edit_space = is_owner or is_platform_admin
    show_membership_notice = not has_space_access and not is_platform_admin

    source_repository = SqlAlchemyUserDataSourceRepository(session)
    data_source_total = source_repository.count_by_research_space(space_id)
    data_sources = source_repository.find_by_research_space(
        space_id,
        skip=0,
        limit=data_source_limit,
    )
    data_sources_response = SpaceOverviewDataSourcesResponse(
        items=[DataSourceResponse.from_entity(item) for item in data_sources],
        total=data_source_total,
        page=1,
        limit=data_source_limit,
        has_next=data_source_total > data_source_limit,
        has_prev=False,
    )

    curation_stats = CurationStatsResponse(total=0, pending=0, approved=0, rejected=0)
    try:
        curation_stats = CurationStatsResponse(
            **curation_service.get_stats(session, str(space_id)),
        )
    except Exception:
        logger.exception(
            "Failed to fetch curation stats for overview",
            extra={"space_id": str(space_id)},
        )

    queue_items_response: list[CurationQueueItemResponse] = []
    try:
        queue_items = curation_service.list_queue(
            session,
            ReviewQuery(
                research_space_id=str(space_id),
                limit=queue_limit,
                offset=0,
            ),
        )
        queue_items_response = [
            CurationQueueItemResponse(
                id=item.id,
                entity_type=item.entity_type,
                entity_id=item.entity_id,
                status=item.status,
                priority=item.priority,
                quality_score=item.quality_score,
                issues=item.issues,
                last_updated=(
                    item.last_updated.isoformat() if item.last_updated else None
                ),
            )
            for item in queue_items
        ]
    except Exception:
        logger.exception(
            "Failed to fetch curation queue for overview",
            extra={"space_id": str(space_id)},
        )

    curation_queue = CurationQueueResponse(
        items=queue_items_response,
        total=len(queue_items_response),
        skip=0,
        limit=queue_limit,
    )

    return SpaceOverviewResponse(
        space=ResearchSpaceResponse.from_entity(space),
        membership=membership_response,
        access=SpaceOverviewAccessResponse(
            has_space_access=has_space_access,
            can_manage_members=can_manage_members,
            can_edit_space=can_edit_space,
            is_owner=is_owner,
            show_membership_notice=show_membership_notice,
            effective_role=effective_role.value,
        ),
        counts=SpaceOverviewCountsResponse(
            member_count=membership_service.get_space_member_count(space_id),
            data_source_count=data_source_total,
        ),
        data_sources=data_sources_response,
        curation_stats=curation_stats,
        curation_queue=curation_queue,
    )


@research_spaces_router.get(
    "/slug/{slug}",
    response_model=ResearchSpaceResponse,
    summary="Get research space by slug",
    description="Get a research space by slug",
)
def get_space_by_slug(
    slug: str,
    current_user: user.User = Depends(get_current_active_user),
    service: research_space_management_service.ResearchSpaceManagementService = Depends(
        get_research_space_service,
    ),
) -> ResearchSpaceResponse:
    """Get a research space by slug."""
    space = service.get_space_by_slug(slug, current_user.id)
    if not space:
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND,
            detail=f"Research space with slug '{slug}' not found",
        )
    return ResearchSpaceResponse.from_entity(space)


@research_spaces_router.put(
    "/{space_id}",
    response_model=ResearchSpaceResponse,
    summary="Update research space",
    description="Update a research space",
)
def update_space(
    space_id: UUID,
    request: UpdateSpaceRequestModel,
    current_user: user.User = Depends(get_current_active_user),
    service: research_space_management_service.ResearchSpaceManagementService = Depends(
        get_research_space_service,
    ),
) -> ResearchSpaceResponse:
    """Update a research space."""
    try:
        status_enum = None
        if request.status:
            try:
                status_enum = research_space.SpaceStatus(
                    request.status.lower(),
                )
            except ValueError:
                raise HTTPException(
                    status_code=HTTP_400_BAD_REQUEST,
                    detail=f"Invalid status: {request.status}",
                ) from None

        update_request = research_space_management_service.UpdateSpaceRequest(
            name=request.name,
            description=request.description,
            settings=request.settings,
            tags=request.tags,
            status=status_enum,
        )
        try:
            space = service.update_space(space_id, update_request, current_user)
        except GraphServiceClientError as exc:
            raise HTTPException(
                status_code=HTTP_500_INTERNAL_SERVER_ERROR,
                detail=(
                    "Research space was updated but graph-space sync failed: "
                    + (exc.detail or str(exc))
                ),
            ) from exc
        if not space:
            raise HTTPException(
                status_code=HTTP_404_NOT_FOUND,
                detail=f"Research space {space_id} not found or access denied",
            )
        return ResearchSpaceResponse.from_entity(space)
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e


@research_spaces_router.delete(
    "/{space_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete research space",
    description="Delete a research space",
)
def delete_space(
    space_id: UUID,
    current_user: user.User = Depends(get_current_active_user),
    service: research_space_management_service.ResearchSpaceManagementService = Depends(
        get_research_space_service,
    ),
) -> None:
    """Delete a research space."""
    existing_space = service.get_space(space_id, current_user.id)
    if existing_space is None:
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND,
            detail=f"Research space {space_id} not found or access denied",
        )
    try:
        success = service.delete_space(space_id, current_user.id)
    except GraphServiceClientError as exc:
        raise HTTPException(
            status_code=HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Research space was deleted but graph-space archival sync failed: "
                + (exc.detail or str(exc))
            ),
        ) from exc
    if not success:
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND,
            detail=f"Research space {space_id} not found or access denied",
        )
