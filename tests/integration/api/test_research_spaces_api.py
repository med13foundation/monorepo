"""
Integration tests for Research Spaces API endpoints.

Tests API routes, authentication, authorization, and data persistence.
"""

import os
from contextlib import contextmanager
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from src.database import session as session_module
from src.domain.entities.user import UserRole, UserStatus
from src.infrastructure.security.jwt_provider import JWTProvider
from src.main import create_app
from src.models.database import Base
from src.models.database.research_space import (
    ResearchSpaceMembershipModel,
    ResearchSpaceModel,
)
from src.models.database.user import UserModel


def _using_postgres() -> bool:
    return os.getenv("DATABASE_URL", "").startswith("postgresql")


@contextmanager
def _session_for_api(db_session):
    if _using_postgres():
        session = session_module.SessionLocal()
        try:
            yield session
        finally:
            session.close()
    else:
        yield db_session


def _auth_headers(user: UserModel) -> dict[str, str]:
    """Helper to build auth headers for tests.

    Includes both a real JWT (for parity with production) and test headers that
    allow the auth dependency to short-circuit in TESTING environments.
    """
    secret = os.getenv(
        "MED13_DEV_JWT_SECRET",
        "test-jwt-secret-0123456789abcdefghijklmnopqrstuvwxyz",
    )
    provider = JWTProvider(secret_key=secret)
    role_value = user.role.value if isinstance(user.role, UserRole) else user.role
    token = provider.create_access_token(user_id=user.id, role=role_value)
    return {
        "Authorization": f"Bearer {token}",
        "X-TEST-USER-ID": str(user.id),
        "X-TEST-USER-EMAIL": user.email,
        "X-TEST-USER-ROLE": role_value,
    }


@pytest.fixture(scope="function")
def test_client(test_engine):
    """Create a test client for API testing."""
    # Reset schema for clean tests
    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)

    app = create_app()
    client = TestClient(app)
    yield client

    # Cleanup
    Base.metadata.drop_all(bind=test_engine)


@pytest.fixture
def test_user(db_session):
    """Create a test user for authentication."""
    unique_suffix = uuid4().hex
    with _session_for_api(db_session) as session:
        user = UserModel(
            email=f"test-{unique_suffix}@example.com",
            username=f"testuser-{unique_suffix}",
            full_name="Test User",
            hashed_password="hashed_password",
            role=UserRole.RESEARCHER.value,
            status="active",
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        session.expunge(user)
    return user


@pytest.fixture
def test_space(db_session, test_user):
    """Create a test research space."""
    unique_suffix = uuid4().hex
    with _session_for_api(db_session) as session:
        space = ResearchSpaceModel(
            slug=f"test-space-{unique_suffix}",
            name="Test Space",
            description="Test research space",
            owner_id=test_user.id,
            status="active",
        )
        session.add(space)
        session.commit()
        session.refresh(space)
    return space


class TestResearchSpacesAPI:
    """Test research spaces API endpoints."""

    def test_create_space_requires_authentication(self, test_client):
        """Test that creating a space requires authentication."""
        response = test_client.post(
            "/research-spaces",
            json={
                "name": "Test Space",
                "slug": "test-space",
                "description": "Test",
            },
        )
        assert response.status_code == 401

    def test_list_spaces_requires_authentication(self, test_client):
        """Test that listing spaces requires authentication."""
        response = test_client.get("/research-spaces")
        assert response.status_code == 401

    def test_get_space_requires_authentication(self, test_client, test_space):
        """Test that getting a space requires authentication."""
        response = test_client.get(f"/research-spaces/{test_space.id}")
        assert response.status_code == 401

    # Note: Full integration tests would require:
    # - JWT token generation and authentication
    # - Database fixtures with proper relationships
    # - Authorization testing (owner vs member vs non-member)
    # - CRUD operation testing
    # - Membership management testing
    # These are placeholders showing the test structure


class TestMembershipAPI:
    """Test membership management API endpoints."""

    def test_list_members_requires_authentication(self, test_client, test_space):
        """Test that listing members requires authentication."""
        response = test_client.get(f"/research-spaces/{test_space.id}/members")
        assert response.status_code == 401

    def test_invite_member_requires_authentication(self, test_client, test_space):
        """Test that inviting a member requires authentication."""
        response = test_client.post(
            f"/research-spaces/{test_space.id}/members",
            json={
                "user_id": str(uuid4()),
                "role": "viewer",
            },
        )
        assert response.status_code == 401

    def test_get_my_membership_404_when_not_member(
        self,
        test_client,
        db_session,
        test_user,
    ):
        """Current user should get 404 if not a member of the space."""
        with _session_for_api(db_session) as session:
            other_suffix = uuid4().hex
            other_owner = UserModel(
                email=f"owner-{other_suffix}@example.com",
                username=f"owner-{other_suffix}",
                full_name="Owner User",
                hashed_password="hashed_password",
                role=UserRole.RESEARCHER.value,
                status="active",
            )
            session.add(other_owner)
            session.flush()
            other_space = ResearchSpaceModel(
                slug=f"other-space-{other_suffix}",
                name="Other Space",
                description="Another test space",
                owner_id=other_owner.id,
                status="active",
            )
            session.add(other_space)
            session.commit()

        response = test_client.get(
            f"/research-spaces/{other_space.id}/membership/me",
            headers=_auth_headers(test_user),
        )
        assert response.status_code == 404

    def test_get_my_membership_returns_role_when_member(
        self,
        test_client,
        db_session,
        test_space,
        test_user,
    ):
        """Current user should receive their active membership with role."""
        # Seed an active membership for the user as admin
        membership_id = uuid4()
        with _session_for_api(db_session) as session:
            session.execute(
                ResearchSpaceMembershipModel.__table__.insert(),
                {
                    "id": membership_id,
                    "space_id": test_space.id,
                    "user_id": test_user.id,
                    "role": "admin",
                    "invited_by": test_user.id,
                    "invited_at": datetime.now(UTC),
                    "joined_at": datetime.now(UTC),
                    "is_active": True,
                    "created_at": datetime.now(UTC),
                    "updated_at": datetime.now(UTC),
                },
            )
            session.commit()

        response = test_client.get(
            f"/research-spaces/{test_space.id}/membership/me",
            headers=_auth_headers(test_user),
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["id"] == str(membership_id)
        assert payload["role"] == "admin"

    def test_list_members_includes_user_display_details(
        self,
        test_client,
        db_session,
        test_space,
        test_user,
    ):
        """Listing members should include compact user details for display."""
        membership_id = uuid4()
        with _session_for_api(db_session) as session:
            session.execute(
                ResearchSpaceMembershipModel.__table__.insert(),
                {
                    "id": membership_id,
                    "space_id": test_space.id,
                    "user_id": test_user.id,
                    "role": "researcher",
                    "invited_by": test_user.id,
                    "invited_at": datetime.now(UTC),
                    "joined_at": datetime.now(UTC),
                    "is_active": True,
                    "created_at": datetime.now(UTC),
                    "updated_at": datetime.now(UTC),
                },
            )
            session.commit()

        response = test_client.get(
            f"/research-spaces/{test_space.id}/members",
            headers=_auth_headers(test_user),
        )

        assert response.status_code == 200
        payload = response.json()
        membership = payload["memberships"][0]
        assert membership["id"] == str(membership_id)
        assert membership["user"]["id"] == str(test_user.id)
        assert membership["user"]["username"] == test_user.username
        assert membership["user"]["full_name"] == test_user.full_name

    def test_search_invitable_users_returns_active_non_members_only(
        self,
        test_client,
        db_session,
        test_space,
        test_user,
    ):
        """Autocomplete should return active non-members that match the query."""
        unique_suffix = uuid4().hex[:8]
        active_candidate_username = f"candidate-{unique_suffix}"
        suspended_candidate_username = f"candidate-suspended-{unique_suffix}"
        existing_member_username = f"candidate-member-{unique_suffix}"
        with _session_for_api(db_session) as session:
            active_candidate = UserModel(
                email=f"candidate-{unique_suffix}@example.com",
                username=active_candidate_username,
                full_name="Candidate Active",
                hashed_password="hashed_password",
                role=UserRole.RESEARCHER,
                status=UserStatus.ACTIVE,
            )
            suspended_candidate = UserModel(
                email=f"candidate-suspended-{unique_suffix}@example.com",
                username=suspended_candidate_username,
                full_name="Candidate Suspended",
                hashed_password="hashed_password",
                role=UserRole.RESEARCHER,
                status=UserStatus.SUSPENDED,
            )
            existing_member = UserModel(
                email=f"candidate-member-{unique_suffix}@example.com",
                username=existing_member_username,
                full_name="Candidate Member",
                hashed_password="hashed_password",
                role=UserRole.RESEARCHER,
                status=UserStatus.ACTIVE,
            )
            session.add_all([active_candidate, suspended_candidate, existing_member])
            session.flush()
            session.execute(
                ResearchSpaceMembershipModel.__table__.insert(),
                {
                    "id": uuid4(),
                    "space_id": test_space.id,
                    "user_id": existing_member.id,
                    "role": "viewer",
                    "invited_by": test_user.id,
                    "invited_at": datetime.now(UTC),
                    "joined_at": datetime.now(UTC),
                    "is_active": True,
                    "created_at": datetime.now(UTC),
                    "updated_at": datetime.now(UTC),
                },
            )
            session.commit()

        response = test_client.get(
            f"/research-spaces/{test_space.id}/members/search-users",
            params={"query": "candidate"},
            headers=_auth_headers(test_user),
        )

        assert response.status_code == 200
        payload = response.json()
        usernames = [user["username"] for user in payload["users"]]
        assert active_candidate_username in usernames
        assert suspended_candidate_username not in usernames
        assert existing_member_username not in usernames

    # Note: Full integration tests would require:
    # - Authentication fixtures
    # - Authorization testing (admin vs non-admin)
    # - Membership workflow testing (invite, accept, decline)
    # - Role update testing
    # - Member removal testing
