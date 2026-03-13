"""Unit tests for the SQLAlchemy graph space access adapter."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import uuid4

from src.domain.entities.research_space_membership import MembershipRole
from src.domain.entities.user import UserRole, UserStatus
from src.infrastructure.repositories.kernel.kernel_space_access_repository import (
    SqlAlchemyKernelSpaceAccessRepository,
)
from src.models.database.kernel.space_memberships import (
    GraphSpaceMembershipModel,
    GraphSpaceMembershipRoleEnum,
)
from src.models.database.kernel.spaces import GraphSpaceModel, GraphSpaceStatusEnum
from src.models.database.user import UserModel

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


def test_get_effective_role_returns_owner_without_membership(
    db_session: Session,
) -> None:
    owner_id = uuid4()
    space_id = uuid4()

    db_session.add(
        UserModel(
            id=owner_id,
            email=f"{owner_id}@example.org",
            username=f"user_{str(owner_id).replace('-', '')[:8]}",
            full_name="Owner User",
            hashed_password="hashed",
            role=UserRole.RESEARCHER,
            status=UserStatus.ACTIVE,
            email_verified=True,
        ),
    )
    db_session.add(
        GraphSpaceModel(
            id=space_id,
            slug=f"graph-space-{str(space_id).replace('-', '')[:8]}",
            name="Access Test Space",
            description="Access test space",
            owner_id=owner_id,
            status=GraphSpaceStatusEnum.ACTIVE,
            settings={},
        ),
    )
    db_session.flush()

    repository = SqlAlchemyKernelSpaceAccessRepository(db_session)

    assert repository.get_effective_role(space_id, owner_id) == MembershipRole.OWNER


def test_get_effective_role_returns_active_membership_role(
    db_session: Session,
) -> None:
    owner_id = uuid4()
    member_id = uuid4()
    space_id = uuid4()

    db_session.add_all(
        [
            UserModel(
                id=owner_id,
                email=f"{owner_id}@example.org",
                username=f"user_{str(owner_id).replace('-', '')[:8]}",
                full_name="Owner User",
                hashed_password="hashed",
                role=UserRole.RESEARCHER,
                status=UserStatus.ACTIVE,
                email_verified=True,
            ),
            UserModel(
                id=member_id,
                email=f"{member_id}@example.org",
                username=f"user_{str(member_id).replace('-', '')[:8]}",
                full_name="Member User",
                hashed_password="hashed",
                role=UserRole.RESEARCHER,
                status=UserStatus.ACTIVE,
                email_verified=True,
            ),
            GraphSpaceModel(
                id=space_id,
                slug=f"graph-space-{str(space_id).replace('-', '')[:8]}",
                name="Access Test Space",
                description="Access test space",
                owner_id=owner_id,
                status=GraphSpaceStatusEnum.ACTIVE,
                settings={},
            ),
        ],
    )
    db_session.flush()
    db_session.add(
        GraphSpaceMembershipModel(
            id=uuid4(),
            space_id=space_id,
            user_id=member_id,
            role=GraphSpaceMembershipRoleEnum.CURATOR,
            is_active=True,
        ),
    )
    db_session.flush()

    repository = SqlAlchemyKernelSpaceAccessRepository(db_session)

    assert repository.get_effective_role(space_id, member_id) == MembershipRole.CURATOR


def test_get_effective_role_ignores_inactive_membership(
    db_session: Session,
) -> None:
    owner_id = uuid4()
    member_id = uuid4()
    space_id = uuid4()

    db_session.add_all(
        [
            UserModel(
                id=owner_id,
                email=f"{owner_id}@example.org",
                username=f"user_{str(owner_id).replace('-', '')[:8]}",
                full_name="Owner User",
                hashed_password="hashed",
                role=UserRole.RESEARCHER,
                status=UserStatus.ACTIVE,
                email_verified=True,
            ),
            UserModel(
                id=member_id,
                email=f"{member_id}@example.org",
                username=f"user_{str(member_id).replace('-', '')[:8]}",
                full_name="Member User",
                hashed_password="hashed",
                role=UserRole.RESEARCHER,
                status=UserStatus.ACTIVE,
                email_verified=True,
            ),
            GraphSpaceModel(
                id=space_id,
                slug=f"graph-space-{str(space_id).replace('-', '')[:8]}",
                name="Access Test Space",
                description="Access test space",
                owner_id=owner_id,
                status=GraphSpaceStatusEnum.ACTIVE,
                settings={},
            ),
        ],
    )
    db_session.flush()
    db_session.add(
        GraphSpaceMembershipModel(
            id=uuid4(),
            space_id=space_id,
            user_id=member_id,
            role=GraphSpaceMembershipRoleEnum.RESEARCHER,
            is_active=False,
        ),
    )
    db_session.flush()

    repository = SqlAlchemyKernelSpaceAccessRepository(db_session)

    assert repository.get_effective_role(space_id, member_id) is None


def test_get_effective_role_requires_graph_space_registry_entry(
    db_session: Session,
) -> None:
    owner_id = uuid4()
    space_id = uuid4()

    db_session.add(
        UserModel(
            id=owner_id,
            email=f"{owner_id}@example.org",
            username=f"user_{str(owner_id).replace('-', '')[:8]}",
            full_name="Owner User",
            hashed_password="hashed",
            role=UserRole.RESEARCHER,
            status=UserStatus.ACTIVE,
            email_verified=True,
        ),
    )
    db_session.flush()

    repository = SqlAlchemyKernelSpaceAccessRepository(db_session)

    assert repository.get_effective_role(space_id, owner_id) is None
