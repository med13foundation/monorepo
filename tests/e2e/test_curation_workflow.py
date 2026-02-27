import os

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

from src.database.session import SessionLocal, engine
from src.domain.entities.user import UserRole, UserStatus
from src.infrastructure.dependency_injection import container as container_module
from src.infrastructure.security.password_hasher import PasswordHasher
from src.main import create_app
from src.middleware import jwt_auth as jwt_auth_module
from src.models.database.base import Base
from src.models.database.user import UserModel
from tests.db_reset import reset_database

TEST_ADMIN_PASSWORD = os.getenv("MED13_E2E_ADMIN_PASSWORD", "StrongPass!123")

pytestmark = pytest.mark.asyncio(loop_scope="module")


async def _reset_container_services() -> None:
    container = container_module.container
    container._authentication_service = None
    container._authentication_service_loop = None
    container._authorization_service = None
    container._authorization_service_loop = None
    container._user_management_service = None
    container._user_management_service_loop = None
    container._user_repository = None
    container._session_repository = None
    await container.engine.dispose()
    jwt_auth_module.SKIP_JWT_VALIDATION = True


async def _create_admin_user(
    email: str = "admin-e2e@med13.org",
    password: str | None = None,
) -> tuple[str, str]:
    resolved_password = password or TEST_ADMIN_PASSWORD
    session = SessionLocal()
    try:
        session.query(UserModel).filter(UserModel.email == email).delete()
        admin = UserModel(
            email=email,
            username="admin-e2e",
            full_name="E2E Admin",
            hashed_password=PasswordHasher().hash_password(resolved_password),
            role=UserRole.ADMIN,
            status=UserStatus.ACTIVE,
            email_verified=True,
        )
        session.add(admin)
        session.commit()
    finally:
        session.close()

    async with container_module.container.async_session_factory() as async_session:
        await async_session.execute(
            delete(UserModel).where(UserModel.email == email),
        )
        await async_session.execute(
            UserModel.__table__.insert().values(
                email=email,
                username="admin-e2e",
                full_name="E2E Admin",
                hashed_password=PasswordHasher().hash_password(resolved_password),
                role=UserRole.ADMIN,
                status=UserStatus.ACTIVE,
                email_verified=True,
            ),
        )
        await async_session.commit()
    return email, resolved_password


async def _get_auth_headers(client: AsyncClient) -> dict[str, str]:
    email, password = await _create_admin_user()
    resp = await client.post(
        "/auth/login",
        json={"email": email, "password": password},
    )
    assert resp.status_code == 200
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def test_curation_submit_list_approve_comment() -> None:
    await _reset_container_services()
    jwt_auth_module.SKIP_JWT_VALIDATION = True
    try:
        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            reset_database(engine, Base.metadata)
            headers = await _get_auth_headers(client)

            # Submit a record for review
            resp = await client.post(
                "/curation/submit",
                json={"entity_type": "genes", "entity_id": "GENE1", "priority": "high"},
                headers=headers,
            )
            assert resp.status_code == 201, resp.json()
            created_id = resp.json()["id"]
            assert isinstance(created_id, int)

            # List queue and ensure our item appears
            resp = await client.get(
                "/curation/queue",
                params={"entity_type": "genes", "status": "pending"},
                headers=headers,
            )
            assert resp.status_code == 200, resp.json()
            items = resp.json()
            assert any(item["id"] == created_id for item in items)

            # Approve the item
            resp = await client.post(
                "/curation/bulk",
                json={"ids": [created_id], "action": "approve"},
                headers=headers,
            )
            assert resp.status_code == 200, resp.json()
            assert resp.json()["updated"] >= 1

            # Leave a comment
            resp = await client.post(
                "/curation/comment",
                json={
                    "entity_type": "genes",
                    "entity_id": "GENE1",
                    "comment": "Looks good",
                    "user": "tester",
                },
                headers=headers,
            )
            assert resp.status_code == 201, resp.json()
            assert isinstance(resp.json()["id"], int)
    finally:
        jwt_auth_module.SKIP_JWT_VALIDATION = False
