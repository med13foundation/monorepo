"""Unit tests for the SQLAlchemy graph space membership adapter."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from src.domain.entities.research_space_membership import (
    MembershipRole,
    ResearchSpaceMembership,
)
from src.infrastructure.repositories.kernel.kernel_space_membership_repository import (
    SqlAlchemyKernelSpaceMembershipRepository,
)
from src.models.database.kernel.space_memberships import (
    GraphSpaceMembershipModel,
    GraphSpaceMembershipRoleEnum,
)
from src.models.database.kernel.spaces import GraphSpaceModel, GraphSpaceStatusEnum

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


def _create_space(db_session: Session) -> tuple[UUID, UUID]:
    owner_id = uuid4()
    space_id = uuid4()
    db_session.add(
        GraphSpaceModel(
            id=space_id,
            slug=f"graph-space-{str(space_id).replace('-', '')[:8]}",
            name="Graph Membership Space",
            description="Graph membership test space",
            owner_id=owner_id,
            status=GraphSpaceStatusEnum.ACTIVE,
            settings={},
        ),
    )
    db_session.flush()
    return space_id, owner_id


def test_list_for_space_returns_sorted_memberships(
    db_session: Session,
) -> None:
    space_id, _ = _create_space(db_session)
    first_user_id = uuid4()
    second_user_id = uuid4()
    db_session.add_all(
        [
            GraphSpaceMembershipModel(
                id=uuid4(),
                space_id=space_id,
                user_id=second_user_id,
                role=GraphSpaceMembershipRoleEnum.RESEARCHER,
                is_active=True,
            ),
            GraphSpaceMembershipModel(
                id=uuid4(),
                space_id=space_id,
                user_id=first_user_id,
                role=GraphSpaceMembershipRoleEnum.CURATOR,
                is_active=True,
            ),
        ],
    )
    db_session.flush()

    repository = SqlAlchemyKernelSpaceMembershipRepository(db_session)

    memberships = repository.list_for_space(space_id)

    assert [membership.user_id for membership in memberships] == sorted(
        [first_user_id, second_user_id],
    )
    roles_by_user_id = {
        membership.user_id: membership.role for membership in memberships
    }
    assert roles_by_user_id[first_user_id] == MembershipRole.CURATOR


def test_save_upserts_space_membership(
    db_session: Session,
) -> None:
    space_id, _ = _create_space(db_session)
    user_id = uuid4()
    repository = SqlAlchemyKernelSpaceMembershipRepository(db_session)
    now = datetime.now(UTC)

    created = repository.save(
        ResearchSpaceMembership(
            space_id=space_id,
            user_id=user_id,
            role=MembershipRole.RESEARCHER,
            invited_by=None,
            invited_at=None,
            joined_at=None,
            is_active=True,
            created_at=now,
            updated_at=now,
        ),
    )
    updated = repository.save(
        created.with_role(MembershipRole.ADMIN).with_status(is_active=False),
    )

    assert created.user_id == user_id
    assert updated.role == MembershipRole.ADMIN
    assert updated.is_active is False


def test_get_for_space_user_returns_none_when_missing(
    db_session: Session,
) -> None:
    space_id, _ = _create_space(db_session)
    repository = SqlAlchemyKernelSpaceMembershipRepository(db_session)

    assert repository.get_for_space_user(space_id=space_id, user_id=uuid4()) is None


def test_replace_for_space_replaces_active_membership_snapshot(
    db_session: Session,
) -> None:
    space_id, _ = _create_space(db_session)
    retained_user_id = uuid4()
    removed_user_id = uuid4()
    repository = SqlAlchemyKernelSpaceMembershipRepository(db_session)
    now = datetime.now(UTC)

    repository.save(
        ResearchSpaceMembership(
            space_id=space_id,
            user_id=retained_user_id,
            role=MembershipRole.RESEARCHER,
            invited_by=None,
            invited_at=None,
            joined_at=None,
            is_active=True,
            created_at=now,
            updated_at=now,
        ),
    )
    repository.save(
        ResearchSpaceMembership(
            space_id=space_id,
            user_id=removed_user_id,
            role=MembershipRole.CURATOR,
            invited_by=None,
            invited_at=None,
            joined_at=None,
            is_active=True,
            created_at=now,
            updated_at=now,
        ),
    )

    replaced = repository.replace_for_space(
        space_id=space_id,
        memberships=[
            ResearchSpaceMembership(
                space_id=space_id,
                user_id=retained_user_id,
                role=MembershipRole.ADMIN,
                invited_by=None,
                invited_at=None,
                joined_at=None,
                is_active=True,
                created_at=now,
                updated_at=now,
            ),
        ],
    )

    memberships_by_user = {membership.user_id: membership for membership in replaced}
    assert memberships_by_user[retained_user_id].role == MembershipRole.ADMIN
    assert memberships_by_user[retained_user_id].is_active is True
    assert memberships_by_user[removed_user_id].is_active is False
