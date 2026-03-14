"""
Integration tests for the remaining platform-owned research-space routes.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from src.database import session as session_module
from src.database.seeds.seeder import seed_entity_resolution_policies
from src.domain.entities.user import UserRole
from src.domain.services.pubmed_ingestion import PubMedIngestionSummary
from src.infrastructure.security.jwt_provider import JWTProvider
from src.main import create_app
from src.models.database.base import Base
from src.models.database.research_space import ResearchSpaceModel
from src.models.database.user import UserModel
from src.models.database.user_data_source import (
    SourceStatusEnum,
    SourceTypeEnum,
    UserDataSourceModel,
)
from src.routes.research_spaces.dependencies import (
    get_ingestion_scheduling_service_for_space,
)
from tests.db_reset import reset_database

pytestmark = pytest.mark.graph


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
        "AUTH_JWT_SECRET",
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
def researcher_user(db_session) -> UserModel:
    suffix = uuid4().hex
    with _session_for_api(db_session) as session:
        user = UserModel(
            email=f"researcher-{suffix}@example.com",
            username=f"researcher-{suffix}",
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
def space(db_session, researcher_user) -> ResearchSpaceModel:
    suffix = uuid4().hex[:16]
    with _session_for_api(db_session) as session:
        space = ResearchSpaceModel(
            slug=f"kernel-space-{suffix}",
            name="Kernel Space",
            description="Research space used for platform route tests",
            owner_id=researcher_user.id,
            status="active",
        )
        session.add(space)
        session.commit()
        session.refresh(space)
        session.expunge(space)
    return space


def test_space_ingest_runs_only_configured_active_sources(
    test_client,
    db_session,
    researcher_user,
    space,
):
    class FakeIngestionSchedulingService:
        async def trigger_ingestion(self, source_id: UUID) -> PubMedIngestionSummary:
            return PubMedIngestionSummary(
                source_id=source_id,
                fetched_records=4,
                parsed_publications=4,
                created_publications=3,
                updated_publications=1,
                executed_query="MED13[Title/Abstract]",
            )

    test_client.app.dependency_overrides[get_ingestion_scheduling_service_for_space] = (
        lambda: FakeIngestionSchedulingService()
    )

    try:
        headers = _auth_headers(researcher_user)
        source_id = str(uuid4())
        with _session_for_api(db_session) as session:
            session.add(
                UserDataSourceModel(
                    id=source_id,
                    owner_id=str(researcher_user.id),
                    research_space_id=str(space.id),
                    name="PubMed source",
                    description="Configured for ingest",
                    source_type=SourceTypeEnum.PUBMED,
                    status=SourceStatusEnum.ACTIVE,
                    template_id=None,
                    configuration={
                        "metadata": {"query": "MED13"},
                        "requests_per_minute": 10,
                    },
                    ingestion_schedule={
                        "enabled": True,
                        "frequency": "daily",
                        "start_time": None,
                        "timezone": "UTC",
                        "cron_expression": None,
                        "backend_job_id": None,
                        "next_run_at": None,
                        "last_run_at": None,
                    },
                    quality_metrics={},
                    tags=[],
                    version="1.0",
                ),
            )
            session.commit()

        run_one = test_client.post(
            f"/research-spaces/{space.id}/ingest/sources/{source_id}/run",
            headers=headers,
        )
        assert run_one.status_code == 200, run_one.text
        run_one_payload = run_one.json()
        assert run_one_payload["status"] == "completed"
        assert run_one_payload["source_id"] == source_id
        assert run_one_payload["created_publications"] == 3

        run_all = test_client.post(
            f"/research-spaces/{space.id}/ingest/run",
            headers=headers,
        )
        assert run_all.status_code == 200, run_all.text
        run_all_payload = run_all.json()
        assert run_all_payload["total_sources"] == 1
        assert run_all_payload["active_sources"] == 1
        assert run_all_payload["runnable_sources"] == 1
        assert run_all_payload["completed_sources"] == 1
        assert run_all_payload["skipped_sources"] == 0
        assert run_all_payload["failed_sources"] == 0
        assert run_all_payload["runs"][0]["source_id"] == source_id
        assert run_all_payload["runs"][0]["status"] == "completed"
    finally:
        test_client.app.dependency_overrides.pop(
            get_ingestion_scheduling_service_for_space,
            None,
        )


def test_space_curation_stats_and_queue_are_available(
    test_client,
    researcher_user,
    space,
):
    headers = _auth_headers(researcher_user)

    stats_response = test_client.get(
        f"/research-spaces/{space.id}/curation/stats",
        headers=headers,
    )
    assert stats_response.status_code == 200, stats_response.text
    stats_payload = stats_response.json()
    assert stats_payload["total"] == 0
    assert stats_payload["pending"] == 0
    assert stats_payload["approved"] == 0
    assert stats_payload["rejected"] == 0

    queue_response = test_client.get(
        f"/research-spaces/{space.id}/curation/queue",
        headers=headers,
        params={"limit": 5},
    )
    assert queue_response.status_code == 200, queue_response.text
    queue_payload = queue_response.json()
    assert queue_payload["total"] == 0
    assert queue_payload["items"] == []


def test_seed_entity_resolution_policies_runs_without_platform_graph_routes(db_session):
    with _session_for_api(db_session) as session:
        seed_entity_resolution_policies(session)
