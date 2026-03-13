"""Dependencies for research space routes."""

from __future__ import annotations

from collections.abc import Generator
from uuid import UUID

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from src.application.curation.repositories.review_repository import (
    SqlAlchemyReviewRepository,
)
from src.application.curation.services.review_service import ReviewService
from src.application.services import (
    DataSourceActivationService,
    IngestionSchedulingService,
    MembershipManagementService,
    SourceManagementService,
)
from src.application.services.research_space_management_service import (
    ResearchSpaceManagementService,
)
from src.database.session import get_session, set_session_rls_context
from src.domain.entities.research_space_membership import MembershipRole
from src.domain.entities.user import UserRole
from src.infrastructure.graph_service import GraphServiceSpaceLifecycleSync
from src.infrastructure.repositories import (
    SqlAlchemyDataSourceActivationRepository,
    SqlAlchemyResearchSpaceRepository,
    SqlAlchemyUserDataSourceRepository,
)
from src.infrastructure.repositories.research_space_membership_repository import (
    SqlAlchemyResearchSpaceMembershipRepository,
)


def get_research_space_service(
    db: Session = Depends(get_session),
) -> ResearchSpaceManagementService:
    """Get research space management service."""
    space_repository = SqlAlchemyResearchSpaceRepository(session=db)
    membership_repository = SqlAlchemyResearchSpaceMembershipRepository(session=db)
    return ResearchSpaceManagementService(
        research_space_repository=space_repository,
        space_lifecycle_sync=GraphServiceSpaceLifecycleSync(
            membership_repository=membership_repository,
        ),
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
        space_lifecycle_sync=GraphServiceSpaceLifecycleSync(
            membership_repository=membership_repository,
        ),
    )


def get_source_service_for_space(
    session: Session = Depends(get_session),
) -> SourceManagementService:
    """Get source management service instance."""
    source_repository = SqlAlchemyUserDataSourceRepository(session)
    # TODO: Add template repository when needed
    return SourceManagementService(source_repository, None)


def get_activation_service_for_space(
    session: Session = Depends(get_session),
) -> DataSourceActivationService:
    """Return activation policy service for space-scoped permission checks."""
    activation_repository = SqlAlchemyDataSourceActivationRepository(session)
    return DataSourceActivationService(activation_repository)


def get_ingestion_scheduling_service_for_space() -> (
    Generator[IngestionSchedulingService]
):
    """Yield ingestion scheduling service for space-scoped ingestion execution."""
    from src.infrastructure.factories.ingestion_scheduler_factory import (  # noqa: PLC0415
        ingestion_scheduling_service_context,
    )

    with ingestion_scheduling_service_context() as service:
        yield service


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
    is_admin_user = user_role == UserRole.ADMIN
    set_session_rls_context(
        session,
        current_user_id=user_id,
        has_phi_access=is_admin_user,
        is_admin=is_admin_user,
        bypass_rls=False,
    )

    # Platform admins can access any space
    if is_admin_user:
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
    is_admin_user = user_role == UserRole.ADMIN
    set_session_rls_context(
        session,
        current_user_id=user_id,
        has_phi_access=is_admin_user,
        is_admin=is_admin_user,
        bypass_rls=False,
    )

    if is_admin_user:
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
