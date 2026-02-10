from __future__ import annotations

import os
from uuid import uuid4

from fastapi.testclient import TestClient

from src.application.services.authorization_service import AuthorizationError
from src.database.seed import DEFAULT_RESEARCH_SPACE_ID
from src.database.session import SessionLocal, engine
from src.domain.entities.user import User, UserRole, UserStatus
from src.infrastructure.dependency_injection import container as container_module
from src.infrastructure.security.password_hasher import PasswordHasher
from src.main import create_app
from src.middleware import jwt_auth as jwt_auth_module
from src.models.database import Base
from src.models.database.data_discovery import DataDiscoverySessionModel
from src.models.database.research_space import (
    ResearchSpaceModel,
    SpaceStatusEnum,
)
from src.models.database.user import UserModel
from src.routes.auth import get_current_active_user
from tests.db_reset import reset_database


def test_curation_submit_requires_jwt_even_with_api_key() -> None:
    """
    Ensure legacy API keys can no longer bypass JWT authentication on curation routes.
    """
    os.environ.setdefault("MED13_ALLOW_MISSING_API_KEYS", "1")
    os.environ.setdefault("ADMIN_API_KEY", "admin-key-123")

    app = create_app()
    client = TestClient(app)

    response = client.post(
        "/curation/submit",
        headers={"X-API-Key": "admin-key-123"},
        json={"entity_type": "genes", "entity_id": "GENE1", "priority": "high"},
    )

    assert response.status_code == 401


def test_data_discovery_rejects_foreign_session_access() -> None:
    """
    Verify researchers cannot read sessions owned by another user.
    """
    reset_database(engine, Base.metadata)
    session = SessionLocal()

    owner_id = uuid4()
    other_user_id = uuid4()
    session_id = uuid4()

    # Seed default research space ownership to satisfy FK constraints
    session.add(
        UserModel(
            id=owner_id,
            email="owner@example.com",
            username="owner-user",
            full_name="Owner User",
            hashed_password=PasswordHasher().hash_password("StrongPass!123"),
            role=UserRole.RESEARCHER,
            status=UserStatus.ACTIVE,
            email_verified=True,
        ),
    )
    session.add(
        ResearchSpaceModel(
            id=DEFAULT_RESEARCH_SPACE_ID,
            slug="default-space",
            name="Default Space",
            description="Default research space for tests",
            owner_id=owner_id,
            status=SpaceStatusEnum.ACTIVE,
            settings={},
            tags=[],
        ),
    )
    session.commit()

    session.add(
        DataDiscoverySessionModel(
            id=str(session_id),
            owner_id=str(owner_id),
            research_space_id=str(DEFAULT_RESEARCH_SPACE_ID),
            name="Secured Session",
            gene_symbol=None,
            search_term=None,
            selected_sources=[],
            tested_sources=[],
            total_tests_run=0,
            successful_tests=0,
            is_active=True,
        ),
    )
    session.commit()
    session.close()

    other_user = User(
        id=other_user_id,
        email="other@example.com",
        username="other-user",
        full_name="Other User",
        hashed_password=PasswordHasher().hash_password("StrongPass!123"),
        role=UserRole.RESEARCHER,
        status=UserStatus.ACTIVE,
        email_verified=True,
    )

    app = create_app()
    app.dependency_overrides[get_current_active_user] = lambda: other_user
    client = TestClient(app)

    jwt_auth_module.SKIP_JWT_VALIDATION = True
    try:
        response = client.get(
            f"/data-discovery/sessions/{session_id}",
            headers={"Authorization": "Bearer test-token"},
        )
    finally:
        jwt_auth_module.SKIP_JWT_VALIDATION = False
        app.dependency_overrides.pop(get_current_active_user, None)

    assert response.status_code == 403


def _build_active_user(role: UserRole = UserRole.RESEARCHER) -> User:
    return User(
        id=uuid4(),
        email=f"{role.value}@example.com",
        username=f"{role.value}-user",
        full_name="Security Regression User",
        hashed_password=PasswordHasher().hash_password("StrongPass!123"),
        role=role,
        status=UserStatus.ACTIVE,
        email_verified=True,
    )


class _DenyAuthorizationService:
    async def require_permission(self, user_id, permission) -> None:
        message = "Permission denied for test"
        raise AuthorizationError(message)


class _UserServiceStub:
    async def list_users(self, **kwargs):
        message = "list_users should not be invoked when permission is denied"
        raise AssertionError(message)

    async def get_user_statistics(self):
        message = "get_user_statistics should not be invoked when permission is denied"
        raise AssertionError(message)


def test_user_listing_requires_permission_gate() -> None:
    app = create_app()
    overrides = {
        container_module.container.get_authorization_service: lambda: _DenyAuthorizationService(),
        container_module.container.get_user_management_service: lambda: _UserServiceStub(),
        get_current_active_user: lambda: _build_active_user(),
    }
    for dependency, override in overrides.items():
        app.dependency_overrides[dependency] = override

    client = TestClient(app)
    jwt_auth_module.SKIP_JWT_VALIDATION = True
    try:
        response = client.get(
            "/users",
            headers={"Authorization": "Bearer test-token"},
        )
    finally:
        jwt_auth_module.SKIP_JWT_VALIDATION = False
        for dependency in overrides:
            app.dependency_overrides.pop(dependency, None)

    assert response.status_code == 403


def test_user_statistics_requires_audit_permission() -> None:
    app = create_app()
    overrides = {
        container_module.container.get_authorization_service: lambda: _DenyAuthorizationService(),
        container_module.container.get_user_management_service: lambda: _UserServiceStub(),
        get_current_active_user: lambda: _build_active_user(UserRole.CURATOR),
    }
    for dependency, override in overrides.items():
        app.dependency_overrides[dependency] = override

    client = TestClient(app)
    jwt_auth_module.SKIP_JWT_VALIDATION = True
    try:
        response = client.get(
            "/users/stats/overview",
            headers={"Authorization": "Bearer test-token"},
        )
    finally:
        jwt_auth_module.SKIP_JWT_VALIDATION = False
        for dependency in overrides:
            app.dependency_overrides.pop(dependency, None)

    assert response.status_code == 403
