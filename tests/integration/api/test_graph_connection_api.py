"""Integration tests for graph-connection API routes."""

from __future__ import annotations

import os
from contextlib import contextmanager
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from src.application.agents.services.graph_connection_service import (
    GraphConnectionOutcome,
)
from src.database import session as session_module
from src.domain.entities.user import UserRole
from src.infrastructure.security.jwt_provider import JWTProvider
from src.main import create_app
from src.models.database import Base
from src.models.database.research_space import ResearchSpaceModel
from src.models.database.user import UserModel
from src.routes.research_spaces.graph_connection_routes import (
    get_graph_connection_service,
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


class StubGraphConnectionService:
    """Async stub service used for graph-connection endpoint tests."""

    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def discover_connections_for_seed(  # noqa: PLR0913
        self,
        *,
        research_space_id: str,
        seed_entity_id: str,
        source_type: str = "clinvar",
        research_space_settings: dict[str, object] | None = None,
        model_id: str | None = None,
        relation_types: list[str] | None = None,
        max_depth: int = 2,
        shadow_mode: bool | None = None,
    ) -> GraphConnectionOutcome:
        del research_space_settings
        self.calls.append(
            {
                "research_space_id": research_space_id,
                "seed_entity_id": seed_entity_id,
                "source_type": source_type,
                "model_id": model_id,
                "relation_types": relation_types,
                "max_depth": max_depth,
                "shadow_mode": shadow_mode,
            },
        )
        return GraphConnectionOutcome(
            seed_entity_id=seed_entity_id,
            research_space_id=research_space_id,
            status="discovered",
            reason="processed",
            review_required=False,
            shadow_mode=bool(shadow_mode),
            wrote_to_graph=True,
            run_id=str(uuid4()),
            proposed_relations_count=3,
            persisted_relations_count=2,
            rejected_candidates_count=1,
            errors=(),
        )

    async def close(self) -> None:
        return None


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
            email=f"graph-connection-{suffix}@example.com",
            username=f"graph-connection-{suffix}",
            full_name="Graph Connection Researcher",
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
            slug=f"graph-connection-space-{suffix}",
            name="Graph Connection Space",
            description="Research space for graph connection API tests",
            owner_id=researcher_user.id,
            status="active",
        )
        session.add(space)
        session.commit()
        session.refresh(space)
        session.expunge(space)
    return space


def test_graph_connection_batch_requires_authentication(
    test_client: TestClient,
) -> None:
    response = test_client.post(
        f"/research-spaces/{uuid4()}/graph/connections/discover",
        json={"seed_entity_ids": [str(uuid4())]},
    )
    assert response.status_code == 401


def test_graph_connection_single_requires_authentication(
    test_client: TestClient,
) -> None:
    response = test_client.post(
        f"/research-spaces/{uuid4()}/entities/{uuid4()}/connections",
        json={},
    )
    assert response.status_code == 401


def test_graph_connection_batch_endpoint_success(
    researcher_user: UserModel,
    space: ResearchSpaceModel,
) -> None:
    app = create_app()
    service = StubGraphConnectionService()
    app.dependency_overrides[get_graph_connection_service] = lambda: service
    client = TestClient(app)
    seed_a = uuid4()
    seed_b = uuid4()

    response = client.post(
        f"/research-spaces/{space.id}/graph/connections/discover",
        headers=_auth_headers(researcher_user),
        json={
            "seed_entity_ids": [str(seed_a), str(seed_b)],
            "source_type": "pubmed",
            "max_depth": 3,
            "shadow_mode": True,
        },
    )
    app.dependency_overrides.clear()

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["requested"] == 2
    assert payload["processed"] == 2
    assert payload["discovered"] == 2
    assert payload["persisted_relations_count"] == 4
    assert len(payload["outcomes"]) == 2
    assert service.calls
    assert service.calls[0]["research_space_id"] == str(space.id)
    assert service.calls[0]["seed_entity_id"] == str(seed_a)
    assert service.calls[0]["source_type"] == "pubmed"
    assert service.calls[0]["max_depth"] == 3
    assert service.calls[0]["shadow_mode"] is True


def test_graph_connection_single_endpoint_success(
    researcher_user: UserModel,
    space: ResearchSpaceModel,
) -> None:
    app = create_app()
    service = StubGraphConnectionService()
    app.dependency_overrides[get_graph_connection_service] = lambda: service
    client = TestClient(app)
    entity_id = uuid4()

    response = client.post(
        f"/research-spaces/{space.id}/entities/{entity_id}/connections",
        headers=_auth_headers(researcher_user),
        json={"source_type": "clinvar", "max_depth": 2},
    )
    app.dependency_overrides.clear()

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["seed_entity_id"] == str(entity_id)
    assert payload["status"] == "discovered"
    assert payload["wrote_to_graph"] is True
    assert service.calls
    assert service.calls[0]["seed_entity_id"] == str(entity_id)
