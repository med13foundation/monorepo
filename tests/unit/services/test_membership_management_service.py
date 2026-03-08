from unittest.mock import MagicMock
from uuid import UUID, uuid4

from src.application.services.membership_management_service import (
    MembershipManagementService,
    UpdateMemberRoleRequest,
)
from src.domain.entities.research_space import ResearchSpace
from src.domain.entities.research_space_membership import (
    MembershipRole,
    ResearchSpaceMembership,
)


def build_space(owner_id: UUID | None = None) -> ResearchSpace:
    return ResearchSpace(
        id=uuid4(),
        slug="med13-core-space",
        name="MED13 Core Research Space",
        description="Primary research workspace",
        owner_id=owner_id if owner_id is not None else uuid4(),
    )


def build_membership(
    *,
    space_id: UUID | None = None,
    user_id: UUID | None = None,
    role: MembershipRole = MembershipRole.RESEARCHER,
) -> ResearchSpaceMembership:
    return ResearchSpaceMembership(
        id=uuid4(),
        space_id=space_id if space_id is not None else uuid4(),
        user_id=user_id if user_id is not None else uuid4(),
        role=role,
    )


def test_update_member_role_allows_implicit_owner() -> None:
    owner_id = uuid4()
    member_id = uuid4()
    space = build_space(owner_id)
    membership = build_membership(
        space_id=space.id,
        user_id=member_id,
        role=MembershipRole.VIEWER,
    )
    membership_repository = MagicMock()
    membership_repository.find_by_id.return_value = membership
    membership_repository.save.side_effect = (
        lambda updated_membership: updated_membership
    )
    research_space_repository = MagicMock()
    research_space_repository.find_by_id.return_value = space

    service = MembershipManagementService(
        membership_repository=membership_repository,
        research_space_repository=research_space_repository,
    )

    updated = service.update_member_role(
        membership.id,
        UpdateMemberRoleRequest(role=MembershipRole.CURATOR),
        owner_id,
    )

    assert updated is not None
    assert updated.role == MembershipRole.CURATOR
    membership_repository.save.assert_called_once()


def test_update_member_role_allows_platform_admin_without_space_membership() -> None:
    requester_id = uuid4()
    membership = build_membership(role=MembershipRole.RESEARCHER)
    membership_repository = MagicMock()
    membership_repository.find_by_id.return_value = membership
    membership_repository.save.side_effect = (
        lambda updated_membership: updated_membership
    )
    research_space_repository = MagicMock()

    service = MembershipManagementService(
        membership_repository=membership_repository,
        research_space_repository=research_space_repository,
    )

    updated = service.update_member_role(
        membership.id,
        UpdateMemberRoleRequest(role=MembershipRole.ADMIN),
        requester_id,
        requester_is_platform_admin=True,
    )

    assert updated is not None
    assert updated.role == MembershipRole.ADMIN
    membership_repository.save.assert_called_once()
