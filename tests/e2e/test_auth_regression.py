"""
Regression test to ensure authentication remains functional in the test harness.

Verifies that a user seeded into both the synchronous and asynchronous stores can
successfully obtain a JWT via /auth/login. This guards against future regressions
where the DI container points to a different database than SessionLocal.
"""

from __future__ import annotations

import os

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

from src.database import session as db_session
from src.domain.entities.user import UserRole, UserStatus
from src.infrastructure.dependency_injection import container as container_module
from src.infrastructure.security.password_hasher import PasswordHasher
from src.main import create_app
from src.models.database.user import UserModel

pytestmark = pytest.mark.asyncio

TEST_AUTH_PASSWORD = os.getenv("MED13_E2E_ADMIN_PASSWORD", "StrongPass!123")


async def _seed_user(
    email: str = "auth-regression@example.com",
    password: str | None = None,
) -> tuple[str, str]:
    """Seed the same user into sync and async stores."""
    resolved_password = password or TEST_AUTH_PASSWORD
    username = email.split("@")[0]

    # Sync store
    session = db_session.SessionLocal()
    try:
        session.query(UserModel).filter(UserModel.email == email).delete()
        session.add(
            UserModel(
                email=email,
                username=username,
                full_name="Auth Regression",
                hashed_password=PasswordHasher().hash_password(resolved_password),
                role=UserRole.ADMIN,
                status=UserStatus.ACTIVE,
                email_verified=True,
            ),
        )
        session.commit()
    finally:
        session.close()

    # Async store used by the auth service
    async with container_module.container.async_session_factory() as async_session:
        await async_session.execute(delete(UserModel).where(UserModel.email == email))
        await async_session.execute(
            UserModel.__table__.insert().values(
                email=email,
                username=username,
                full_name="Auth Regression",
                hashed_password=PasswordHasher().hash_password(resolved_password),
                role=UserRole.ADMIN,
                status=UserStatus.ACTIVE,
                email_verified=True,
            ),
        )
        await async_session.commit()

    return email, resolved_password


async def test_auth_login_regression(test_engine) -> None:
    """Ensure /auth/login succeeds for a valid user in test env."""
    email, password = await _seed_user()
    app = create_app()
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/auth/login",
            json={"email": email, "password": password},
        )

    assert response.status_code == 200, response.json()
    payload = response.json()
    assert payload.get("access_token")
    assert payload.get("refresh_token")
    assert payload.get("user", {}).get("email") == email


async def test_auth_refresh_regression(test_engine) -> None:
    """Ensure /auth/refresh accepts JSON body refresh_token and returns new tokens."""
    email, password = await _seed_user(email="auth-refresh@example.com")
    app = create_app()
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        login_response = await client.post(
            "/auth/login",
            json={"email": email, "password": password},
        )
        assert login_response.status_code == 200, login_response.json()

        login_payload = login_response.json()
        refresh_token = login_payload.get("refresh_token")
        assert isinstance(refresh_token, str)
        assert refresh_token

        refresh_response = await client.post(
            "/auth/refresh",
            json={"refresh_token": refresh_token},
        )

    assert refresh_response.status_code == 200, refresh_response.json()
    refresh_payload = refresh_response.json()
    assert refresh_payload.get("access_token")
    assert refresh_payload.get("refresh_token")
