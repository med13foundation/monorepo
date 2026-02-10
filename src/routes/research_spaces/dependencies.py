"""Dependencies for research space routes."""

from __future__ import annotations

from uuid import UUID

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from src.application.curation.repositories.review_repository import (
    SqlAlchemyReviewRepository,
)
from src.application.curation.services.review_service import ReviewService
from src.application.services.membership_management_service import (
    MembershipManagementService,
)
from src.application.services.research_space_management_service import (
    ResearchSpaceManagementService,
)
from src.application.services.source_management_service import (
    SourceManagementService,
)
from src.database.session import get_session
from src.domain.entities.research_space_membership import MembershipRole
from src.domain.entities.user import UserRole
from src.infrastructure.repositories.research_space_membership_repository import (
    SqlAlchemyResearchSpaceMembershipRepository,
)
from src.infrastructure.repositories.research_space_repository import (
    SqlAlchemyResearchSpaceRepository,
)
from src.infrastructure.repositories.user_data_source_repository import (
    SqlAlchemyUserDataSourceRepository,
)


def get_research_space_service(
    db: Session = Depends(get_session),
) -> ResearchSpaceManagementService:
    """Get research space management service."""
    space_repository = SqlAlchemyResearchSpaceRepository(session=db)
    return ResearchSpaceManagementService(
        research_space_repository=space_repository,
    )


def get_membership_service(
    db: Session = Depends(get_session),
) -> MembershipManagementService:
    """Get membership management service."""
    membership_repository = SqlAlchemyResearchSpaceMembershipRepository(session=db)
    space_repository = SqlAlchemyResearchSpaceRepository(session=db)
    return MembershipManagementService(
        membership_repository=membership_repository,
        research_space_repository=space_repository,
    )


def get_source_service_for_space(
    session: Session = Depends(get_session),
) -> SourceManagementService:
    """Get source management service instance."""
    source_repository = SqlAlchemyUserDataSourceRepository(session)
    # TODO: Add template repository when needed
    return SourceManagementService(source_repository, None)


def verify_space_membership(
    space_id: UUID,
    user_id: UUID,
    membership_service: MembershipManagementService,
    session: Session,
    user_role: UserRole | None = None,
) -> None:
    """
    Verify that a user is a member of a research space.

    Checks both explicit membership and ownership.
    Raises HTTPException if user is not a member or owner.
    """
    # Platform admins can access any space
    if user_role == UserRole.ADMIN:
        return

    # Check if user is an explicit member
    if membership_service.is_user_member(space_id, user_id):
        return

    # Check if user is the owner of the space
    space_repository = SqlAlchemyResearchSpaceRepository(session=session)
    space = space_repository.find_by_id(space_id)
    if space and space.owner_id == user_id:
        return

    # User is neither a member nor the owner
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="User is not a member of this research space",
    )


def verify_space_role(
    space_id: UUID,
    user_id: UUID,
    required_role: MembershipRole,
    membership_service: MembershipManagementService,
    session: Session,
    user_role: UserRole | None = None,
) -> None:
    """
    Verify that a user has the required role or higher in a research space.

    Platform admins and space owners are always allowed.
    """
    if user_role == UserRole.ADMIN:
        return

    membership_role = membership_service.get_user_role(space_id, user_id)
    if membership_role is None:
        space_repository = SqlAlchemyResearchSpaceRepository(session=session)
        space = space_repository.find_by_id(space_id)
        if space and space.owner_id == user_id:
            return
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User does not have access to this research space",
        )

    role_hierarchy = {
        MembershipRole.VIEWER: 1,
        MembershipRole.RESEARCHER: 2,
        MembershipRole.CURATOR: 3,
        MembershipRole.ADMIN: 4,
        MembershipRole.OWNER: 5,
    }
    if role_hierarchy[membership_role] < role_hierarchy[required_role]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User lacks permission for this operation",
        )


def require_curator_role(
    space_id: UUID,
    user_id: UUID,
    membership_service: MembershipManagementService,
    session: Session,
    user_role: UserRole | None = None,
) -> None:
    """Require curator-level access for space-scoped operations."""
    verify_space_role(
        space_id,
        user_id,
        MembershipRole.CURATOR,
        membership_service,
        session,
        user_role,
    )


def require_researcher_role(
    space_id: UUID,
    user_id: UUID,
    membership_service: MembershipManagementService,
    session: Session,
    user_role: UserRole | None = None,
) -> None:
    """Require researcher-level access for space-scoped operations."""
    verify_space_role(
        space_id,
        user_id,
        MembershipRole.RESEARCHER,
        membership_service,
        session,
        user_role,
    )


def get_curation_service(session: Session = Depends(get_session)) -> ReviewService:
    """Get curation review service instance."""
    repository = SqlAlchemyReviewRepository()
    return ReviewService(repository)
