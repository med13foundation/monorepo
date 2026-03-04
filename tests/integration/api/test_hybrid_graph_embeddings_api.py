"""Integration tests for hybrid graph + embedding API endpoints."""

from __future__ import annotations

import os
from contextlib import contextmanager
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from src.database import session as session_module
from src.database.seeds.seeder import (
    seed_entity_resolution_policies,
    seed_relation_constraints,
)
from src.domain.entities.user import UserRole
from src.infrastructure.security.jwt_provider import JWTProvider
from src.main import create_app
from src.models.database import Base
from src.models.database.research_space import ResearchSpaceModel
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


def _create_entity(
    *,
    test_client: TestClient,
    space_id: UUID,
    headers: dict[str, str],
    entity_type: str,
    display_label: str,
    namespace: str,
    value: str,
) -> UUID:
    response = test_client.post(
        f"/research-spaces/{space_id}/entities",
        headers=headers,
        json={
            "entity_type": entity_type,
            "display_label": display_label,
            "metadata": {},
            "identifiers": {namespace: value},
        },
    )
    assert response.status_code == 201, response.text
    return UUID(response.json()["entity"]["id"])


def _create_relation(
    *,
    test_client: TestClient,
    space_id: UUID,
    headers: dict[str, str],
    source_id: UUID,
    target_id: UUID,
) -> UUID:
    response = test_client.post(
        f"/research-spaces/{space_id}/relations",
        headers=headers,
        json={
            "source_id": str(source_id),
            "relation_type": "ASSOCIATED_WITH",
            "target_id": str(target_id),
            "confidence": 0.82,
            "evidence_summary": "Deterministic relation for suggestion exclusion test.",
            "evidence_tier": "LITERATURE",
            "provenance_id": None,
        },
    )
    assert response.status_code == 201, response.text
    return UUID(response.json()["id"])


@contextmanager
def _hybrid_flags(*, entity_embeddings: str, relation_suggestions: str):
    previous_entity_embeddings = os.environ.get("MED13_ENABLE_ENTITY_EMBEDDINGS")
    previous_relation_suggestions = os.environ.get("MED13_ENABLE_RELATION_SUGGESTIONS")
    os.environ["MED13_ENABLE_ENTITY_EMBEDDINGS"] = entity_embeddings
    os.environ["MED13_ENABLE_RELATION_SUGGESTIONS"] = relation_suggestions
    try:
        yield
    finally:
        if previous_entity_embeddings is None:
            os.environ.pop("MED13_ENABLE_ENTITY_EMBEDDINGS", None)
        else:
            os.environ["MED13_ENABLE_ENTITY_EMBEDDINGS"] = previous_entity_embeddings

        if previous_relation_suggestions is None:
            os.environ.pop("MED13_ENABLE_RELATION_SUGGESTIONS", None)
        else:
            os.environ["MED13_ENABLE_RELATION_SUGGESTIONS"] = (
                previous_relation_suggestions
            )


def test_similar_entities_requires_feature_flag(
    test_client: TestClient,
    db_session,
    researcher_user: UserModel,
    space: ResearchSpaceModel,
) -> None:
    headers = _auth_headers(researcher_user)
    with _session_for_api(db_session) as session:
        seed_entity_resolution_policies(session)

    source_id = _create_entity(
        test_client=test_client,
        space_id=space.id,
        headers=headers,
        entity_type="GENE",
        display_label="MED13",
        namespace="hgnc_id",
        value=f"HGNC:{uuid4().hex[:8]}",
    )

    with _hybrid_flags(entity_embeddings="0", relation_suggestions="0"):
        response = test_client.get(
            f"/research-spaces/{space.id}/entities/{source_id}/similar",
            headers=headers,
            params={"min_similarity": 0.0},
        )

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail["code"] == "FEATURE_DISABLED"


def test_similar_entities_returns_embedding_not_ready(
    test_client: TestClient,
    db_session,
    researcher_user: UserModel,
    space: ResearchSpaceModel,
) -> None:
    headers = _auth_headers(researcher_user)
    with _session_for_api(db_session) as session:
        seed_entity_resolution_policies(session)

    source_id = _create_entity(
        test_client=test_client,
        space_id=space.id,
        headers=headers,
        entity_type="GENE",
        display_label="MED13",
        namespace="hgnc_id",
        value=f"HGNC:{uuid4().hex[:8]}",
    )
    _create_entity(
        test_client=test_client,
        space_id=space.id,
        headers=headers,
        entity_type="GENE",
        display_label="MED13 mediator subunit",
        namespace="hgnc_id",
        value=f"HGNC:{uuid4().hex[:8]}",
    )

    with _hybrid_flags(entity_embeddings="1", relation_suggestions="0"):
        response = test_client.get(
            f"/research-spaces/{space.id}/entities/{source_id}/similar",
            headers=headers,
            params={"min_similarity": 0.0},
        )

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail["code"] == "EMBEDDING_NOT_READY"


def test_similar_entities_returns_ranked_results_after_refresh(
    test_client: TestClient,
    db_session,
    researcher_user: UserModel,
    space: ResearchSpaceModel,
) -> None:
    headers = _auth_headers(researcher_user)
    with _session_for_api(db_session) as session:
        seed_entity_resolution_policies(session)

    source_id = _create_entity(
        test_client=test_client,
        space_id=space.id,
        headers=headers,
        entity_type="GENE",
        display_label="MED13 mediator complex subunit",
        namespace="hgnc_id",
        value=f"HGNC:{uuid4().hex[:8]}",
    )
    candidate_id = _create_entity(
        test_client=test_client,
        space_id=space.id,
        headers=headers,
        entity_type="GENE",
        display_label="MED13 complex mediator protein",
        namespace="hgnc_id",
        value=f"HGNC:{uuid4().hex[:8]}",
    )

    with _hybrid_flags(entity_embeddings="1", relation_suggestions="0"):
        refresh_response = test_client.post(
            f"/research-spaces/{space.id}/entities/embeddings/refresh",
            headers=headers,
            json={
                "entity_ids": [str(source_id), str(candidate_id)],
                "limit": 10,
            },
        )
        assert refresh_response.status_code == 200, refresh_response.text
        assert refresh_response.json()["processed"] == 2

        similar_response = test_client.get(
            f"/research-spaces/{space.id}/entities/{source_id}/similar",
            headers=headers,
            params={"min_similarity": 0.0, "limit": 10},
        )

    assert similar_response.status_code == 200, similar_response.text
    payload = similar_response.json()
    assert payload["source_entity_id"] == str(source_id)
    assert payload["total"] >= 1
    result_ids = {item["entity_id"] for item in payload["results"]}
    assert str(candidate_id) in result_ids
    first_result = payload["results"][0]
    assert "vector_score" in first_result["score_breakdown"]
    assert "graph_overlap_score" in first_result["score_breakdown"]


def test_relation_suggestions_requires_feature_flag(
    test_client: TestClient,
    db_session,
    researcher_user: UserModel,
    space: ResearchSpaceModel,
) -> None:
    headers = _auth_headers(researcher_user)
    with _session_for_api(db_session) as session:
        seed_entity_resolution_policies(session)

    source_id = _create_entity(
        test_client=test_client,
        space_id=space.id,
        headers=headers,
        entity_type="GENE",
        display_label="MED13",
        namespace="hgnc_id",
        value=f"HGNC:{uuid4().hex[:8]}",
    )

    with _hybrid_flags(entity_embeddings="1", relation_suggestions="0"):
        response = test_client.post(
            f"/research-spaces/{space.id}/graph/relation-suggestions",
            headers=headers,
            json={
                "source_entity_ids": [str(source_id)],
                "min_score": 0.0,
            },
        )

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail["code"] == "FEATURE_DISABLED"


def test_relation_suggestions_exclude_existing_relations_and_enforce_constraints(
    test_client: TestClient,
    db_session,
    researcher_user: UserModel,
    space: ResearchSpaceModel,
) -> None:
    headers = _auth_headers(researcher_user)
    with _session_for_api(db_session) as session:
        seed_entity_resolution_policies(session)
        seed_relation_constraints(session)

    source_id = _create_entity(
        test_client=test_client,
        space_id=space.id,
        headers=headers,
        entity_type="GENE",
        display_label="MED13",
        namespace="hgnc_id",
        value=f"HGNC:{uuid4().hex[:8]}",
    )
    existing_target_id = _create_entity(
        test_client=test_client,
        space_id=space.id,
        headers=headers,
        entity_type="PHENOTYPE",
        display_label="Cardiomyopathy",
        namespace="hpo_id",
        value=f"HP:{uuid4().hex[:7]}",
    )
    suggested_target_id = _create_entity(
        test_client=test_client,
        space_id=space.id,
        headers=headers,
        entity_type="PHENOTYPE",
        display_label="Arrhythmia",
        namespace="hpo_id",
        value=f"HP:{uuid4().hex[:7]}",
    )

    _create_relation(
        test_client=test_client,
        space_id=space.id,
        headers=headers,
        source_id=source_id,
        target_id=existing_target_id,
    )

    with _hybrid_flags(entity_embeddings="1", relation_suggestions="1"):
        refresh_response = test_client.post(
            f"/research-spaces/{space.id}/entities/embeddings/refresh",
            headers=headers,
            json={
                "entity_ids": [
                    str(source_id),
                    str(existing_target_id),
                    str(suggested_target_id),
                ],
                "limit": 10,
            },
        )
        assert refresh_response.status_code == 200, refresh_response.text

        suggestion_response = test_client.post(
            f"/research-spaces/{space.id}/graph/relation-suggestions",
            headers=headers,
            json={
                "source_entity_ids": [str(source_id)],
                "limit_per_source": 10,
                "min_score": 0.0,
                "allowed_relation_types": ["ASSOCIATED_WITH"],
                "target_entity_types": ["PHENOTYPE"],
                "exclude_existing_relations": True,
            },
        )

    assert suggestion_response.status_code == 200, suggestion_response.text
    payload = suggestion_response.json()
    assert payload["total"] >= 1
    targets = {item["target_entity_id"] for item in payload["suggestions"]}
    assert str(existing_target_id) not in targets
    assert str(suggested_target_id) in targets
    for item in payload["suggestions"]:
        assert item["relation_type"] == "ASSOCIATED_WITH"
        assert item["constraint_check"]["passed"] is True


def test_relation_suggestions_returns_constraint_config_missing_when_filters_exclude_all(
    test_client: TestClient,
    db_session,
    researcher_user: UserModel,
    space: ResearchSpaceModel,
) -> None:
    headers = _auth_headers(researcher_user)
    with _session_for_api(db_session) as session:
        seed_entity_resolution_policies(session)
        seed_relation_constraints(session)

    source_id = _create_entity(
        test_client=test_client,
        space_id=space.id,
        headers=headers,
        entity_type="GENE",
        display_label="MED13",
        namespace="hgnc_id",
        value=f"HGNC:{uuid4().hex[:8]}",
    )

    with _hybrid_flags(entity_embeddings="1", relation_suggestions="1"):
        refresh_response = test_client.post(
            f"/research-spaces/{space.id}/entities/embeddings/refresh",
            headers=headers,
            json={"entity_ids": [str(source_id)], "limit": 10},
        )
        assert refresh_response.status_code == 200, refresh_response.text

        response = test_client.post(
            f"/research-spaces/{space.id}/graph/relation-suggestions",
            headers=headers,
            json={
                "source_entity_ids": [str(source_id)],
                "allowed_relation_types": ["NOT_A_REAL_RELATION"],
                "min_score": 0.0,
            },
        )

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail["code"] == "CONSTRAINT_CONFIG_MISSING"


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
            email=f"hybrid-researcher-{suffix}@example.com",
            username=f"hybrid-researcher-{suffix}",
            full_name="Hybrid Graph Researcher",
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
def space(db_session, researcher_user: UserModel) -> ResearchSpaceModel:
    suffix = uuid4().hex[:16]
    with _session_for_api(db_session) as session:
        research_space = ResearchSpaceModel(
            slug=f"hybrid-space-{suffix}",
            name="Hybrid Graph Space",
            description="Research space for hybrid graph embedding API tests",
            owner_id=researcher_user.id,
            status="active",
        )
        session.add(research_space)
        session.commit()
        session.refresh(research_space)
        session.expunge(research_space)
    return research_space
