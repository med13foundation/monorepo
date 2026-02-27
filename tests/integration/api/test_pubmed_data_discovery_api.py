"""
Integration tests covering PubMed discovery routes.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from src.database.session import SessionLocal, engine
from src.domain.entities.user import User, UserRole, UserStatus
from src.infrastructure.security.password_hasher import PasswordHasher
from src.main import create_app
from src.middleware import jwt_auth as jwt_auth_module
from src.models.database import Base
from src.models.database.data_discovery import (
    DataDiscoverySessionModel,
    DiscoveryPresetModel,
    PresetScopeEnum,
)
from src.models.database.research_space import ResearchSpaceModel
from src.models.database.user import UserModel
from src.routes.auth import get_current_active_user
from tests.db_reset import reset_database

if TYPE_CHECKING:
    from collections.abc import Callable


def _reset_database() -> None:
    reset_database(engine, Base.metadata)


def _create_user(session: SessionLocal) -> UUID:
    user_id = uuid4()
    user = UserModel(
        id=user_id,
        email="discovery-user@example.com",
        username="discovery-user",
        full_name="Discovery User",
        hashed_password=PasswordHasher().hash_password("StrongPassword!123"),
        role=UserRole.RESEARCHER,
        status=UserStatus.ACTIVE,
        email_verified=True,
    )
    session.add(user)
    session.commit()
    return user_id


def _create_space(
    session: SessionLocal,
    owner_id: UUID,
    slug: str | None = None,
    name: str | None = None,
) -> UUID:
    space_id = uuid4()
    space = ResearchSpaceModel(
        id=space_id,
        slug=slug or "pubmed-space",
        name=name or "PubMed Research",
        description="Space for advanced PubMed discovery",
        owner_id=owner_id,
        status="active",
    )
    session.add(space)
    session.commit()
    return space_id


def _add_preset(
    session: SessionLocal,
    *,
    owner_id: UUID,
    name: str,
    scope: PresetScopeEnum,
    research_space_id: UUID | None = None,
) -> UUID:
    preset_id = uuid4()
    preset = DiscoveryPresetModel(
        id=str(preset_id),
        owner_id=str(owner_id),
        scope=scope,
        provider="pubmed",
        name=name,
        description=f"{name} description",
        parameters={
            "gene_symbol": "MED13",
            "search_term": "syndrome",
            "max_results": 25,
        },
        metadata_payload={},
        research_space_id=str(research_space_id) if research_space_id else None,
    )
    session.add(preset)
    session.commit()
    return preset_id


def _create_discovery_session(
    session: SessionLocal,
    *,
    owner_id: UUID,
    research_space_id: UUID | None = None,
) -> UUID:
    session_id = uuid4()
    space_id = research_space_id or _create_space(
        session,
        owner_id,
        slug=f"session-space-{uuid4()}",
        name="Integration Space",
    )
    record = DataDiscoverySessionModel(
        id=str(session_id),
        owner_id=str(owner_id),
        research_space_id=str(space_id),
        name="Integration Session",
        gene_symbol="MED13",
        search_term="syndrome",
        selected_sources=["pubmed-primary"],
        tested_sources=[],
        pubmed_search_config={
            "gene_symbol": "MED13",
            "search_term": "syndrome",
            "max_results": 10,
        },
        total_tests_run=0,
        successful_tests=0,
        is_active=True,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        last_activity_at=datetime.now(UTC),
    )
    session.add(record)
    session.commit()
    return session_id


def _build_active_user(user_id: UUID) -> User:
    return User(
        id=user_id,
        email="discovery-user@example.com",
        username="discovery-user",
        full_name="Discovery User",
        hashed_password="",
        role=UserRole.RESEARCHER,
        status=UserStatus.ACTIVE,
        email_verified=True,
    )


def _build_client(user_id: UUID) -> tuple[TestClient, Callable[[], None]]:
    app = create_app()
    jwt_auth_module.SKIP_JWT_VALIDATION = True
    app.dependency_overrides[get_current_active_user] = lambda: _build_active_user(
        user_id,
    )
    client = TestClient(app)

    def cleanup() -> None:
        app.dependency_overrides.pop(get_current_active_user, None)
        jwt_auth_module.SKIP_JWT_VALIDATION = False

    return client, cleanup


def test_pubmed_presets_include_space_scope() -> None:
    _reset_database()
    session = SessionLocal()
    user_id = _create_user(session)
    space_id = _create_space(session, user_id)
    _add_preset(
        session,
        owner_id=user_id,
        name="Personal Query",
        scope=PresetScopeEnum.USER,
    )
    _add_preset(
        session,
        owner_id=user_id,
        name="Shared Query",
        scope=PresetScopeEnum.SPACE,
        research_space_id=space_id,
    )
    session.close()

    client, cleanup = _build_client(user_id)
    try:
        response = client.get("/data-discovery/pubmed/presets")
        assert response.status_code == 200
        general_payload = response.json()
        assert len(general_payload) == 2

        response = client.get(
            f"/data-discovery/pubmed/presets?research_space_id={space_id}",
        )
        payload = response.json()
        assert response.status_code == 200
        assert len(payload) == 2
        assert {preset["name"] for preset in payload} == {
            "Personal Query",
            "Shared Query",
        }
    finally:
        cleanup()


def test_create_pubmed_preset_persists_record() -> None:
    _reset_database()
    session = SessionLocal()
    user_id = _create_user(session)
    session.close()

    client, cleanup = _build_client(user_id)
    try:
        payload = {
            "name": "Cardio Set",
            "description": "Focus on atrial defects",
            "scope": "user",
            "research_space_id": None,
            "parameters": {
                "gene_symbol": "MED13L",
                "search_term": "atrial",
                "date_from": "2024-01-01",
                "date_to": None,
                "publication_types": [],
                "languages": [],
                "sort_by": "relevance",
                "max_results": 25,
                "additional_terms": None,
            },
        }
        response = client.post("/data-discovery/pubmed/presets", json=payload)
        assert response.status_code == 201
        preset_id = response.json()["id"]
    finally:
        cleanup()

    session = SessionLocal()
    try:
        stored = session.get(DiscoveryPresetModel, str(preset_id))
        assert stored is not None
        assert stored.name == "Cardio Set"
        assert stored.parameters["gene_symbol"] == "MED13L"
    finally:
        session.close()


def test_pubmed_search_endpoints_create_and_fetch_jobs() -> None:
    _reset_database()
    session = SessionLocal()
    user_id = _create_user(session)
    session_id = _create_discovery_session(session, owner_id=user_id)
    session.close()

    client, cleanup = _build_client(user_id)
    try:
        payload = {
            "session_id": str(session_id),
            "parameters": {
                "gene_symbol": "MED13",
                "search_term": "syndrome",
                "date_from": None,
                "date_to": None,
                "publication_types": [],
                "languages": [],
                "sort_by": "relevance",
                "max_results": 5,
                "additional_terms": None,
            },
        }
        response = client.post("/data-discovery/pubmed/search", json=payload)
        assert response.status_code == 202
        job_payload = response.json()
        job_id = job_payload["id"]
        assert job_payload["owner_id"] == str(user_id)
        assert job_payload["status"] in {"running", "completed"}

        detail_response = client.get(f"/data-discovery/pubmed/search/{job_id}")
        assert detail_response.status_code == 200
        detail_payload = detail_response.json()
        assert detail_payload["id"] == job_id
        assert detail_payload["parameters"]["gene_symbol"] == "MED13"
    finally:
        cleanup()
