"""Integration tests for Tier-2 content enrichment API routes."""

from __future__ import annotations

import os
from contextlib import contextmanager
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from src.application.agents.services.content_enrichment_service import (
    ContentEnrichmentDocumentOutcome,
    ContentEnrichmentRunSummary,
)
from src.database import session as session_module
from src.domain.entities.user import UserRole
from src.infrastructure.security.jwt_provider import JWTProvider
from src.main import create_app
from src.models.database import Base
from src.models.database.research_space import ResearchSpaceModel
from src.models.database.user import UserModel
from src.routes.research_spaces.content_enrichment_routes import (
    get_content_enrichment_service,
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


class StubContentEnrichmentService:
    """Async stub service used for endpoint integration tests."""

    def __init__(self) -> None:
        self.batch_calls: list[dict[str, object]] = []
        self.document_calls: list[dict[str, object]] = []

    async def process_pending_documents(  # noqa: PLR0913
        self,
        *,
        limit: int = 25,
        source_id: UUID | None = None,
        research_space_id: UUID | None = None,
        source_type: str | None = None,
        model_id: str | None = None,
    ) -> ContentEnrichmentRunSummary:
        self.batch_calls.append(
            {
                "limit": limit,
                "source_id": source_id,
                "research_space_id": research_space_id,
                "source_type": source_type,
                "model_id": model_id,
            },
        )
        now = datetime.now(UTC)
        return ContentEnrichmentRunSummary(
            requested=1,
            processed=1,
            enriched=1,
            skipped=0,
            failed=0,
            ai_runs=0,
            deterministic_runs=1,
            errors=(),
            started_at=now,
            completed_at=now,
        )

    async def process_document(
        self,
        *,
        document_id: UUID,
        model_id: str | None = None,
        force: bool = False,
    ) -> ContentEnrichmentDocumentOutcome:
        self.document_calls.append(
            {
                "document_id": document_id,
                "model_id": model_id,
                "force": force,
            },
        )
        return ContentEnrichmentDocumentOutcome(
            document_id=document_id,
            status="enriched",
            execution_mode="deterministic",
            reason="enriched",
            acquisition_method="pass_through",
            content_storage_key="documents/key.txt",
            content_length_chars=42,
            run_id=str(uuid4()),
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
            slug=f"enrichment-space-{suffix}",
            name="Enrichment Space",
            description="Research space for content enrichment API tests",
            owner_id=researcher_user.id,
            status="active",
        )
        session.add(space)
        session.commit()
        session.refresh(space)
        session.expunge(space)
    return space


def test_content_enrichment_batch_requires_authentication(
    test_client: TestClient,
) -> None:
    response = test_client.post(
        f"/research-spaces/{uuid4()}/documents/enrichment/run",
        json={"limit": 5},
    )
    assert response.status_code == 401


def test_content_enrichment_single_requires_authentication(
    test_client: TestClient,
) -> None:
    response = test_client.post(
        f"/research-spaces/{uuid4()}/documents/{uuid4()}/enrichment",
        json={"force": False},
    )
    assert response.status_code == 401


def test_content_enrichment_batch_endpoint_success(
    researcher_user: UserModel,
    space: ResearchSpaceModel,
) -> None:
    app = create_app()
    service = StubContentEnrichmentService()
    app.dependency_overrides[get_content_enrichment_service] = lambda: service
    client = TestClient(app)

    response = client.post(
        f"/research-spaces/{space.id}/documents/enrichment/run",
        headers=_auth_headers(researcher_user),
        json={"limit": 3, "source_type": "pubmed"},
    )
    app.dependency_overrides.clear()

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["requested"] == 1
    assert payload["processed"] == 1
    assert payload["enriched"] == 1
    assert service.batch_calls
    assert service.batch_calls[0]["research_space_id"] == space.id
    assert service.batch_calls[0]["limit"] == 3
    assert service.batch_calls[0]["source_type"] == "pubmed"


def test_content_enrichment_single_endpoint_success(
    researcher_user: UserModel,
    space: ResearchSpaceModel,
) -> None:
    app = create_app()
    service = StubContentEnrichmentService()
    app.dependency_overrides[get_content_enrichment_service] = lambda: service
    client = TestClient(app)
    document_id = uuid4()

    response = client.post(
        f"/research-spaces/{space.id}/documents/{document_id}/enrichment",
        headers=_auth_headers(researcher_user),
        json={"force": True},
    )
    app.dependency_overrides.clear()

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["document_id"] == str(document_id)
    assert payload["status"] == "enriched"
    assert payload["content_length_chars"] == 42
    assert service.document_calls
    assert service.document_calls[0]["document_id"] == document_id
    assert service.document_calls[0]["force"] is True
