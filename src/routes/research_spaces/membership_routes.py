"""Membership management routes for research spaces."""

from __future__ import annotations

from uuid import UUID

from fastapi import Depends, HTTPException, Query

from src.application.services.membership_management_service import (
    InviteMemberRequest,
    MembershipManagementService,
    UpdateMemberRoleRequest,
)
from src.domain.entities.research_space_membership import MembershipRole
from src.domain.entities.user import User, UserRole
from src.routes.auth import get_current_active_user
from src.routes.research_spaces.dependencies import get_membership_service
from src.routes.research_spaces.schemas import (
    InviteMemberRequestModel,
    MembershipListResponse,
    MembershipResponse,
    UpdateMemberRoleRequestModel,
)

from .router import (
    HTTP_201_CREATED,
    HTTP_400_BAD_REQUEST,
    HTTP_404_NOT_FOUND,
    research_spaces_router,
)


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
        return MembershipResponse.from_entity(membership)
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
) -> MembershipListResponse:
    """List all members of a research space."""
    memberships = service.get_space_members(space_id, skip, limit)
    return MembershipListResponse(
        memberships=[MembershipResponse.from_entity(m) for m in memberships],
        total=len(memberships),
        skip=skip,
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
        return MembershipResponse.from_entity(membership)
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
) -> MembershipResponse:
    """Accept a pending invitation."""
    membership = service.accept_invitation(membership_id, current_user.id)
    if not membership:
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND,
            detail="Invitation not found or already accepted",
        )
    return MembershipResponse.from_entity(membership)


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
) -> MembershipListResponse:
    """Get all pending invitations for the current user."""
    memberships = service.get_pending_invitations(current_user.id, skip, limit)
    return MembershipListResponse(
        memberships=[MembershipResponse.from_entity(m) for m in memberships],
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
        )

    membership = service.get_membership_for_user(space_id, current_user.id)
    if membership is None:
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND,
            detail="Membership not found or inactive",
        )
    return MembershipResponse.from_entity(membership)
