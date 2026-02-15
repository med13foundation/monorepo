"""Integration tests for admin audit APIs."""

from __future__ import annotations

import json
import os
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from src.database import session as session_module
from src.domain.entities.user import UserRole
from src.infrastructure.security.jwt_provider import JWTProvider
from src.main import create_app
from src.models.database.audit import AuditLog
from src.models.database.base import Base
from src.models.database.user import UserModel
from tests.db_reset import reset_database


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
    secret = os.getenv(
        "MED13_DEV_JWT_SECRET",
        "test-jwt-secret-0123456789abcdefghijklmnopqrstuvwxyz",
    )
    provider = JWTProvider(secret_key=secret)
    role_value = user.role.value if isinstance(user.role, UserRole) else str(user.role)
    token = provider.create_access_token(user_id=user.id, role=role_value)
    return {
        "Authorization": f"Bearer {token}",
        "X-TEST-USER-ID": str(user.id),
        "X-TEST-USER-EMAIL": user.email,
        "X-TEST-USER-ROLE": role_value,
    }


@pytest.fixture(scope="function")
def test_client(test_engine):
    db_engine = session_module.engine if _using_postgres() else test_engine
    reset_database(db_engine, Base.metadata)

    app = create_app()
    client = TestClient(app)
    yield client

    reset_database(db_engine, Base.metadata)


@pytest.fixture
def admin_user(db_session) -> UserModel:
    suffix = uuid4().hex
    with _session_for_api(db_session) as session:
        user = UserModel(
            email=f"admin-audit-{suffix}@example.com",
            username=f"admin-audit-{suffix}",
            full_name="Admin Audit User",
            hashed_password="hashed_password",
            role=UserRole.ADMIN.value,
            status="active",
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        session.expunge(user)
    return user


@pytest.fixture
def researcher_user(db_session) -> UserModel:
    suffix = uuid4().hex
    with _session_for_api(db_session) as session:
        user = UserModel(
            email=f"researcher-audit-{suffix}@example.com",
            username=f"researcher-audit-{suffix}",
            full_name="Researcher Audit User",
            hashed_password="hashed_password",
            role=UserRole.RESEARCHER.value,
            status="active",
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        session.expunge(user)
    return user


def test_admin_audit_logs_requires_permission(
    test_client,
    db_session,
    admin_user,
    researcher_user,
):
    marker = f"audit-perm-{uuid4().hex}"
    with _session_for_api(db_session) as session:
        session.add(
            AuditLog(
                action="phi.read",
                entity_type="integration_audit",
                entity_id=marker,
                user=str(admin_user.id),
                success=True,
                details=None,
            ),
        )
        session.commit()

    unauthenticated = test_client.get("/admin/audit/logs")
    assert unauthenticated.status_code == 401

    forbidden = test_client.get(
        "/admin/audit/logs",
        headers=_auth_headers(researcher_user),
    )
    assert forbidden.status_code == 403

    allowed = test_client.get(
        "/admin/audit/logs",
        headers=_auth_headers(admin_user),
        params={"entity_id": marker},
    )
    assert allowed.status_code == 200, allowed.text
    payload = allowed.json()
    assert payload["total"] >= 1
    assert any(item["entity_id"] == marker for item in payload["logs"])


def test_admin_audit_export_supports_json_and_csv(test_client, db_session, admin_user):
    marker = f"audit-export-{uuid4().hex}"
    with _session_for_api(db_session) as session:
        session.add_all(
            [
                AuditLog(
                    action="phi.read",
                    entity_type="integration_export",
                    entity_id=marker,
                    user=str(admin_user.id),
                    success=True,
                    details='{"kind":"read"}',
                ),
                AuditLog(
                    action="phi.update",
                    entity_type="integration_export",
                    entity_id=marker,
                    user=str(admin_user.id),
                    success=True,
                    details='{"kind":"update"}',
                ),
            ],
        )
        session.commit()

    csv_export = test_client.get(
        "/admin/audit/logs/export",
        headers=_auth_headers(admin_user),
        params={
            "entity_type": "integration_export",
            "entity_id": marker,
            "export_format": "csv",
        },
    )
    assert csv_export.status_code == 200, csv_export.text
    assert csv_export.headers["content-type"].startswith("text/csv")
    assert csv_export.text.startswith("id,created_at,action")
    assert marker in csv_export.text

    json_export = test_client.get(
        "/admin/audit/logs/export",
        headers=_auth_headers(admin_user),
        params={
            "entity_type": "integration_export",
            "entity_id": marker,
            "export_format": "json",
        },
    )
    assert json_export.status_code == 200, json_export.text
    assert json_export.headers["content-type"].startswith("application/json")
    decoded = json.loads(json_export.text)
    assert isinstance(decoded, list)
    assert len(decoded) >= 2
    assert all(item["entity_id"] == marker for item in decoded)


def test_admin_audit_retention_cleanup_endpoint(
    test_client,
    db_session,
    admin_user,
    researcher_user,
):
    marker = f"audit-retention-{uuid4().hex}"
    now = datetime.now(UTC)
    old_timestamp = now - timedelta(days=4000)

    with _session_for_api(db_session) as session:
        session.add_all(
            [
                AuditLog(
                    action="phi.read",
                    entity_type="integration_retention",
                    entity_id=f"{marker}-old",
                    user=str(admin_user.id),
                    success=True,
                    details=None,
                    created_at=old_timestamp,
                ),
                AuditLog(
                    action="phi.read",
                    entity_type="integration_retention",
                    entity_id=f"{marker}-new",
                    user=str(admin_user.id),
                    success=True,
                    details=None,
                    created_at=now,
                ),
            ],
        )
        session.commit()

    forbidden = test_client.post(
        "/admin/audit/logs/retention/run",
        headers=_auth_headers(researcher_user),
        json={"retention_days": 2190, "batch_size": 100},
    )
    assert forbidden.status_code == 403

    response = test_client.post(
        "/admin/audit/logs/retention/run",
        headers=_auth_headers(admin_user),
        json={"retention_days": 2190, "batch_size": 100},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["retention_days"] == 2190
    assert payload["batch_size"] == 100
    assert payload["deleted_rows"] >= 1

    with _session_for_api(db_session) as session:
        old_count = session.execute(
            select(func.count())
            .select_from(AuditLog)
            .where(AuditLog.entity_id == f"{marker}-old"),
        ).scalar_one()
        new_count = session.execute(
            select(func.count())
            .select_from(AuditLog)
            .where(AuditLog.entity_id == f"{marker}-new"),
        ).scalar_one()

    assert int(old_count) == 0
    assert int(new_count) == 1
