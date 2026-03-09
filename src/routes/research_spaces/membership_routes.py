"""Membership management routes for research spaces."""

from __future__ import annotations

from uuid import UUID

from fastapi import Depends, HTTPException, Query
from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session

from src.application.services.membership_management_service import (
    InviteMemberRequest,
    MembershipManagementService,
    UpdateMemberRoleRequest,
)
from src.database.session import get_session
from src.domain.entities.research_space_membership import (
    MembershipRole,
    ResearchSpaceMembership,
)
from src.domain.entities.user import User, UserRole, UserStatus
from src.models.database.research_space import (
    ResearchSpaceMembershipModel,
    ResearchSpaceModel,
)
from src.models.database.user import UserModel
from src.routes.auth import get_current_active_user
from src.routes.research_spaces.dependencies import (
    get_membership_service,
    verify_space_membership,
    verify_space_role,
)
from src.routes.research_spaces.schemas import (
    InvitableUserSearchResponse,
    InviteMemberRequestModel,
    MembershipListResponse,
    MembershipResponse,
    MembershipUserResponse,
    UpdateMemberRoleRequestModel,
)

from .router import (
    HTTP_201_CREATED,
    HTTP_400_BAD_REQUEST,
    HTTP_404_NOT_FOUND,
    research_spaces_router,
)


def _coerce_user_model_id(user_id: object) -> UUID:
    """Normalize ORM user IDs to UUIDs at the API boundary."""
    if isinstance(user_id, UUID):
        return user_id
    return UUID(str(user_id))


def _build_membership_user_map(
    session: Session,
    memberships: list[ResearchSpaceMembership],
) -> dict[UUID, MembershipUserResponse]:
    """Load compact user details for the membership collection in one query."""
    unique_user_ids = {membership.user_id for membership in memberships}
    if not unique_user_ids:
        return {}

    result = session.execute(
        select(UserModel).where(UserModel.id.in_(unique_user_ids)),
    )
    user_models = result.scalars().all()
    return {
        _coerce_user_model_id(user_model.id): MembershipUserResponse(
            id=_coerce_user_model_id(user_model.id),
            email=user_model.email,
            username=user_model.username,
            full_name=user_model.full_name,
        )
        for user_model in user_models
    }


def _build_membership_responses(
    memberships: list[ResearchSpaceMembership],
    users_by_id: dict[UUID, MembershipUserResponse],
) -> list[MembershipResponse]:
    """Attach compact user details to each membership in the collection."""
    return [
        MembershipResponse.from_entity(
            membership,
            user=users_by_id.get(membership.user_id),
        )
        for membership in memberships
    ]


def _build_user_search_pattern(query: str) -> str:
    """Build a SQL ILIKE pattern for autocomplete matching."""
    return f"%{query.strip()}%"


@research_spaces_router.post(
    "/{space_id}/members",
    response_model=MembershipResponse,
    summary="Invite member",
    description="Invite a user to join a research space",
    status_code=HTTP_201_CREATED,
)
def invite_member(
    space_id: UUID,
    request: InviteMemberRequestModel,
    current_user: User = Depends(get_current_active_user),
    service: MembershipManagementService = Depends(get_membership_service),
    session: Session = Depends(get_session),
) -> MembershipResponse:
    """Invite a user to join a research space."""
    try:
        try:
            role = MembershipRole(request.role.lower())
        except ValueError:
            raise HTTPException(
                status_code=HTTP_400_BAD_REQUEST,
                detail=f"Invalid role: {request.role}",
            ) from None

        invite_request = InviteMemberRequest(
            space_id=space_id,
            user_id=request.user_id,
            role=role,
            invited_by=current_user.id,
            invited_by_is_platform_admin=current_user.role == UserRole.ADMIN,
        )
        membership = service.invite_member(invite_request)
        users_by_id = _build_membership_user_map(session, [membership])
        return MembershipResponse.from_entity(
            membership,
            user=users_by_id.get(membership.user_id),
        )
    except ValueError as e:
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e


@research_spaces_router.get(
    "/{space_id}/members",
    response_model=MembershipListResponse,
    summary="List space members",
    description="Get all members of a research space",
)
def list_space_members(
    space_id: UUID,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    current_user: User = Depends(get_current_active_user),
    service: MembershipManagementService = Depends(get_membership_service),
    session: Session = Depends(get_session),
) -> MembershipListResponse:
    """List all members of a research space."""
    verify_space_membership(
        space_id,
        current_user.id,
        service,
        session,
        current_user.role,
    )
    memberships = service.get_space_members(space_id, skip, limit)
    users_by_id = _build_membership_user_map(session, memberships)
    return MembershipListResponse(
        memberships=_build_membership_responses(memberships, users_by_id),
        total=len(memberships),
        skip=skip,
        limit=limit,
    )


@research_spaces_router.get(
    "/{space_id}/members/search-users",
    response_model=InvitableUserSearchResponse,
    summary="Search active users to invite",
    description="Search active system users who are not already members of the research space.",
)
def search_invitable_users(
    space_id: UUID,
    query: str = Query(..., min_length=1, max_length=100),
    limit: int = Query(8, ge=1, le=20),
    current_user: User = Depends(get_current_active_user),
    service: MembershipManagementService = Depends(get_membership_service),
    session: Session = Depends(get_session),
) -> InvitableUserSearchResponse:
    """Return active users eligible to be invited to the space."""
    verify_space_role(
        space_id,
        current_user.id,
        MembershipRole.ADMIN,
        service,
        session,
        current_user.role,
    )

    normalized_query = query.strip()
    if normalized_query == "":
        return InvitableUserSearchResponse(
            query="",
            users=[],
            total=0,
            limit=limit,
        )

    existing_member_ids = select(ResearchSpaceMembershipModel.user_id).where(
        ResearchSpaceMembershipModel.space_id == space_id,
    )
    space_owner_id = (
        select(ResearchSpaceModel.owner_id)
        .where(ResearchSpaceModel.id == space_id)
        .scalar_subquery()
    )
    lowered_query = normalized_query.lower()
    lowered_prefix = f"{lowered_query}%"
    search_pattern = _build_user_search_pattern(normalized_query)

    result = session.execute(
        select(UserModel)
        .where(UserModel.status == UserStatus.ACTIVE)
        .where(UserModel.id.notin_(existing_member_ids))
        .where(UserModel.id != space_owner_id)
        .where(
            or_(
                UserModel.username.ilike(search_pattern),
                UserModel.full_name.ilike(search_pattern),
                UserModel.email.ilike(search_pattern),
            ),
        )
        .order_by(
            case(
                (func.lower(UserModel.username) == lowered_query, 0),
                (func.lower(UserModel.username).like(lowered_prefix), 1),
                (func.lower(UserModel.full_name).like(lowered_prefix), 2),
                (func.lower(UserModel.email).like(lowered_prefix), 3),
                else_=4,
            ),
            func.lower(UserModel.username),
            func.lower(UserModel.full_name),
        )
        .limit(limit),
    )
    user_models = result.scalars().all()
    users = [
        MembershipUserResponse(
            id=_coerce_user_model_id(user_model.id),
            email=user_model.email,
            username=user_model.username,
            full_name=user_model.full_name,
        )
        for user_model in user_models
    ]
    return InvitableUserSearchResponse(
        query=normalized_query,
        users=users,
        total=len(users),
        limit=limit,
    )


@research_spaces_router.put(
    "/{space_id}/members/{membership_id}/role",
    response_model=MembershipResponse,
    summary="Update member role",
    description="Update a member's role in a research space",
)
def update_member_role(
    space_id: UUID,
    membership_id: UUID,
    request: UpdateMemberRoleRequestModel,
    current_user: User = Depends(get_current_active_user),
    service: MembershipManagementService = Depends(get_membership_service),
    session: Session = Depends(get_session),
) -> MembershipResponse:
    """Update a member's role in a research space."""
    try:
        try:
            role = MembershipRole(request.role.lower())
        except ValueError:
            raise HTTPException(
                status_code=HTTP_400_BAD_REQUEST,
                detail=f"Invalid role: {request.role}",
            ) from None

        update_request = UpdateMemberRoleRequest(role=role)
        membership = service.update_member_role(
            membership_id,
            update_request,
            current_user.id,
            requester_is_platform_admin=current_user.role == UserRole.ADMIN,
        )
        if not membership:
            raise HTTPException(
                status_code=HTTP_404_NOT_FOUND,
                detail="Membership not found or access denied",
            )
        users_by_id = _build_membership_user_map(session, [membership])
        return MembershipResponse.from_entity(
            membership,
            user=users_by_id.get(membership.user_id),
        )
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e


@research_spaces_router.delete(
    "/{space_id}/members/{membership_id}",
    summary="Remove member",
    description="Remove a member from a research space",
)
def remove_member(
    space_id: UUID,
    membership_id: UUID,
    current_user: User = Depends(get_current_active_user),
    service: MembershipManagementService = Depends(get_membership_service),
) -> None:
    """Remove a member from a research space."""
    success = service.remove_member(
        membership_id,
        current_user.id,
        requester_is_platform_admin=current_user.role == UserRole.ADMIN,
    )
    if not success:
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND,
            detail="Membership not found or access denied",
        )


@research_spaces_router.post(
    "/{space_id}/members/{membership_id}/accept",
    response_model=MembershipResponse,
    summary="Accept invitation",
    description="Accept a pending research space invitation",
)
def accept_invitation(
    membership_id: UUID,
    current_user: User = Depends(get_current_active_user),
    service: MembershipManagementService = Depends(get_membership_service),
    session: Session = Depends(get_session),
) -> MembershipResponse:
    """Accept a pending invitation."""
    membership = service.accept_invitation(membership_id, current_user.id)
    if not membership:
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND,
            detail="Invitation not found or already accepted",
        )
    users_by_id = _build_membership_user_map(session, [membership])
    return MembershipResponse.from_entity(
        membership,
        user=users_by_id.get(membership.user_id),
    )


@research_spaces_router.get(
    "/me/pending-invitations",
    response_model=MembershipListResponse,
    summary="Pending invitations",
    description="Get pending invitations for the current user",
)
def get_pending_invitations(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    current_user: User = Depends(get_current_active_user),
    service: MembershipManagementService = Depends(get_membership_service),
    session: Session = Depends(get_session),
) -> MembershipListResponse:
    """Get all pending invitations for the current user."""
    memberships = service.get_pending_invitations(current_user.id, skip, limit)
    users_by_id = _build_membership_user_map(session, memberships)
    return MembershipListResponse(
        memberships=_build_membership_responses(memberships, users_by_id),
        total=len(memberships),
        skip=skip,
        limit=limit,
    )


@research_spaces_router.get(
    "/{space_id}/membership/me",
    response_model=MembershipResponse,
    summary="Get current user's membership for a space",
    description="Returns the active membership for the authenticated user in the specified research space.",
)
def get_my_membership(
    space_id: UUID,
    current_user: User = Depends(get_current_active_user),
    service: MembershipManagementService = Depends(get_membership_service),
    session: Session = Depends(get_session),
) -> MembershipResponse:
    """Get the current user's membership for a space."""
    # Platform admins have implicit admin membership for support tasks
    if current_user.role == UserRole.ADMIN:
        return MembershipResponse(
            id=UUID(int=0),
            space_id=space_id,
            user_id=current_user.id,
            role=MembershipRole.ADMIN.value,
            invited_by=None,
            invited_at=None,
            joined_at=None,
            is_active=True,
            created_at=(
                current_user.created_at.isoformat()
                if hasattr(current_user, "created_at") and current_user.created_at
                else ""
            ),
            updated_at=(
                current_user.updated_at.isoformat()
                if hasattr(current_user, "updated_at") and current_user.updated_at
                else ""
            ),
            user=MembershipUserResponse.from_user(current_user),
        )

    membership = service.get_membership_for_user(space_id, current_user.id)
    if membership is None:
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND,
            detail="Membership not found or inactive",
        )
    users_by_id = _build_membership_user_map(session, [membership])
    return MembershipResponse.from_entity(
        membership,
        user=users_by_id.get(membership.user_id),
    )
