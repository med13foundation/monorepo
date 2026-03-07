"""Integration tests for Artana observability APIs."""

from __future__ import annotations

import os
from contextlib import contextmanager
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from src.database import session as session_module
from src.domain.entities.user import UserRole
from src.infrastructure.security.jwt_provider import JWTProvider
from src.main import create_app
from src.models.database.base import Base
from src.models.database.research_space import (
    MembershipRoleEnum,
    ResearchSpaceMembershipModel,
    ResearchSpaceModel,
)
from src.models.database.user import UserModel
from src.routes.admin_routes.artana_runs import get_admin_artana_observability_service
from src.routes.research_spaces.artana_run_routes import (
    get_artana_observability_service,
)
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


class _StubObservabilityService:
    def list_admin_runs(self, **_: object) -> dict[str, object]:
        return {
            "runs": [
                {
                    "run_id": "run-1",
                    "space_id": "space-1",
                    "source_ids": ["source-1"],
                    "source_type": "pubmed",
                    "status": "running",
                    "current_stage": "extraction",
                    "updated_at": "2026-03-07T12:00:00+00:00",
                    "started_at": "2026-03-07T11:55:00+00:00",
                    "last_event_type": "model_requested",
                    "alert_count": 1,
                    "alert_codes": ["stuck_run"],
                },
            ],
            "total": 1,
            "page": 1,
            "per_page": 25,
            "counters": {
                "running": 1,
                "failed": 0,
                "stuck": 1,
                "drift_detected": 0,
                "budget_warning": 0,
                "tool_unknown_outcome": 0,
            },
        }

    def get_admin_run_trace(self, *, run_id: str) -> dict[str, object]:
        return _build_trace_payload(run_id=run_id, include_events=False)

    def get_space_run_trace(self, *, space_id, run_id: str) -> dict[str, object]:
        _ = space_id
        return _build_trace_payload(run_id=run_id, include_events=True)


def _build_trace_payload(*, run_id: str, include_events: bool) -> dict[str, object]:
    return {
        "requested_run_id": run_id,
        "run_id": "resolved-run-1",
        "candidate_run_ids": ["resolved-run-1"],
        "space_id": "space-1",
        "source_ids": ["source-1"],
        "source_types": ["pubmed"],
        "status": "running",
        "last_event_seq": 4,
        "last_event_type": "run_summary",
        "progress_percent": 72,
        "current_stage": "extraction",
        "completed_stages": ["ingestion", "enrichment"],
        "started_at": "2026-03-07T11:50:00+00:00",
        "updated_at": "2026-03-07T12:00:00+00:00",
        "eta_seconds": 90,
        "blocked_on": None,
        "failure_reason": None,
        "error_category": None,
        "explain": {"cost_total": 0.2, "drift_count": 0},
        "alerts": [
            {
                "code": "stuck_run",
                "severity": "warning",
                "title": "Run may be stuck",
                "description": "No recent updates.",
                "triggered_at": "2026-03-07T12:00:00+00:00",
                "metadata": {},
            },
        ],
        "events": (
            [
                {
                    "seq": 4,
                    "event_id": "event-4",
                    "event_type": "run_summary",
                    "timestamp": "2026-03-07T12:00:00+00:00",
                    "parent_step_key": None,
                    "step_key": "extract",
                    "tool_name": None,
                    "tool_outcome": None,
                    "payload": {"summary_type": "trace::cost"},
                },
            ]
            if include_events
            else []
        ),
        "summaries": (
            [
                {
                    "summary_type": "trace::cost",
                    "timestamp": "2026-03-07T12:00:00+00:00",
                    "step_key": "extract",
                    "payload": {"total_cost": 0.2, "budget_usd_limit": 1.0},
                },
            ]
            if include_events
            else []
        ),
        "linked_records": [
            {
                "record_type": "source_document",
                "record_id": "doc-1",
                "research_space_id": "space-1",
                "source_id": "source-1",
                "document_id": "doc-1",
                "source_type": "pubmed",
                "status": "extracted",
                "label": "PMID-40214304",
                "created_at": "2026-03-07T11:51:00+00:00",
                "updated_at": "2026-03-07T11:59:00+00:00",
                "metadata": {},
            },
        ],
        "raw_tables": [] if not include_events else None,
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
    with _session_for_api(db_session) as session:
        user = UserModel(
            email=f"artana-admin-{uuid4().hex}@example.com",
            username=f"artana-admin-{uuid4().hex[:10]}",
            full_name="Admin User",
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
    with _session_for_api(db_session) as session:
        user = UserModel(
            email=f"artana-researcher-{uuid4().hex}@example.com",
            username=f"artana-researcher-{uuid4().hex[:10]}",
            full_name="Researcher User",
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
def outsider_user(db_session) -> UserModel:
    with _session_for_api(db_session) as session:
        user = UserModel(
            email=f"artana-outsider-{uuid4().hex}@example.com",
            username=f"artana-outsider-{uuid4().hex[:10]}",
            full_name="Outsider User",
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
def space(db_session, researcher_user) -> ResearchSpaceModel:
    with _session_for_api(db_session) as session:
        space = ResearchSpaceModel(
            slug=f"artana-space-{uuid4().hex[:12]}",
            name="Artana Space",
            description="Artana API test space",
            owner_id=researcher_user.id,
            status="active",
        )
        session.add(space)
        session.commit()
        session.refresh(space)
        session.execute(
            ResearchSpaceMembershipModel.__table__.insert(),
            {
                "id": uuid4(),
                "space_id": space.id,
                "user_id": researcher_user.id,
                "role": MembershipRoleEnum.RESEARCHER.value,
                "is_active": True,
            },
        )
        session.commit()
        session.refresh(space)
        session.expunge(space)
    return space


def test_admin_artana_routes_require_admin_permission(
    test_client: TestClient,
    admin_user: UserModel,
    researcher_user: UserModel,
) -> None:
    app = create_app()
    app.dependency_overrides[get_admin_artana_observability_service] = (
        lambda: _StubObservabilityService()
    )
    client = TestClient(app)

    unauthenticated = client.get("/admin/artana/runs")
    assert unauthenticated.status_code == 401

    forbidden = client.get(
        "/admin/artana/runs",
        headers=_auth_headers(researcher_user),
    )
    assert forbidden.status_code == 403

    allowed = client.get(
        "/admin/artana/runs",
        headers=_auth_headers(admin_user),
    )
    assert allowed.status_code == 200, allowed.text
    assert allowed.json()["runs"][0]["run_id"] == "run-1"

    detail = client.get(
        "/admin/artana/runs/run-1",
        headers=_auth_headers(admin_user),
    )
    app.dependency_overrides.clear()

    assert detail.status_code == 200, detail.text
    payload = detail.json()
    assert payload["requested_run_id"] == "run-1"
    assert payload["events"] == []
    assert payload["summaries"] == []


def test_space_artana_route_enforces_membership_and_returns_trace_payload(
    outsider_user: UserModel,
    researcher_user: UserModel,
    space: ResearchSpaceModel,
) -> None:
    app = create_app()
    app.dependency_overrides[get_artana_observability_service] = (
        lambda: _StubObservabilityService()
    )
    client = TestClient(app)

    forbidden = client.get(
        f"/research-spaces/{space.id}/artana-runs/pipeline-1",
        headers=_auth_headers(outsider_user),
    )
    assert forbidden.status_code == 403

    allowed = client.get(
        f"/research-spaces/{space.id}/artana-runs/pipeline-1",
        headers=_auth_headers(researcher_user),
    )
    app.dependency_overrides.clear()

    assert allowed.status_code == 200, allowed.text
    payload = allowed.json()
    assert payload["requested_run_id"] == "pipeline-1"
    assert payload["run_id"] == "resolved-run-1"
    assert payload["events"][0]["event_type"] == "run_summary"
    assert payload["linked_records"][0]["record_type"] == "source_document"
