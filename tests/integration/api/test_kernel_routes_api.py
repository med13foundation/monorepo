"""
Integration tests for kernel API routes (entities/observations/relations + admin dictionary).
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from src.database import session as session_module
from src.domain.entities.user import UserRole
from src.infrastructure.security.jwt_provider import JWTProvider
from src.main import create_app
from src.models.database.base import Base
from src.models.database.kernel.dictionary import (
    RelationConstraintModel,
    VariableSynonymModel,
)
from src.models.database.research_space import ResearchSpaceModel
from src.models.database.user import UserModel


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
    """Build auth headers for tests (JWT + test bypass headers)."""
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
    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)

    app = create_app()
    client = TestClient(app)
    yield client

    Base.metadata.drop_all(bind=test_engine)


@pytest.fixture
def admin_user(db_session) -> UserModel:
    suffix = uuid4().hex
    with _session_for_api(db_session) as session:
        user = UserModel(
            email=f"admin-{suffix}@example.com",
            username=f"admin-{suffix}",
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
            description="Research space used for kernel route tests",
            owner_id=researcher_user.id,
            status="active",
        )
        session.add(space)
        session.commit()
        session.refresh(space)
        session.expunge(space)
    return space


def test_admin_dictionary_requires_admin_role(test_client, admin_user, researcher_user):
    resp = test_client.get("/admin/dictionary/variables")
    assert resp.status_code == 401

    resp = test_client.get(
        "/admin/dictionary/variables",
        headers=_auth_headers(researcher_user),
    )
    assert resp.status_code == 403

    resp = test_client.get(
        "/admin/dictionary/variables",
        headers=_auth_headers(admin_user),
    )
    assert resp.status_code == 200


def test_kernel_entity_observation_relation_flow(
    test_client,
    db_session,
    admin_user,
    researcher_user,
    space,
):
    # 1) Create a minimal variable definition (admin)
    resp = test_client.post(
        "/admin/dictionary/variables",
        headers=_auth_headers(admin_user),
        json={
            "id": "VAR_TEST_NOTE",
            "canonical_name": "test_note",
            "display_name": "Test Note",
            "data_type": "STRING",
            "domain_context": "general",
            "sensitivity": "INTERNAL",
            "preferred_unit": None,
            "constraints": {},
            "description": "Test variable for kernel route integration",
        },
    )
    assert resp.status_code == 201, resp.text

    # 2) Create two entities in the space (researcher/owner)
    headers = _auth_headers(researcher_user)

    gene_resp = test_client.post(
        f"/research-spaces/{space.id}/entities",
        headers=headers,
        json={
            "entity_type": "GENE",
            "display_label": "MED13",
            "metadata": {},
            "identifiers": {"hgnc_id": "HGNC:12345"},
        },
    )
    assert gene_resp.status_code == 201, gene_resp.text
    gene_payload = gene_resp.json()
    gene_id = UUID(gene_payload["entity"]["id"])

    pheno_resp = test_client.post(
        f"/research-spaces/{space.id}/entities",
        headers=headers,
        json={
            "entity_type": "PHENOTYPE",
            "display_label": "Developmental delay",
            "metadata": {},
            "identifiers": {"hpo_id": "HP:0001263"},
        },
    )
    assert pheno_resp.status_code == 201, pheno_resp.text
    pheno_id = UUID(pheno_resp.json()["entity"]["id"])

    # 3) Record an observation on the gene entity
    obs_resp = test_client.post(
        f"/research-spaces/{space.id}/observations",
        headers=headers,
        json={
            "subject_id": str(gene_id),
            "variable_id": "VAR_TEST_NOTE",
            "value": "hello kernel",
            "unit": None,
            "observed_at": None,
            "provenance_id": None,
            "confidence": 1.0,
        },
    )
    assert obs_resp.status_code == 201, obs_resp.text

    list_obs = test_client.get(
        f"/research-spaces/{space.id}/observations",
        headers=headers,
        params={"subject_id": str(gene_id)},
    )
    assert list_obs.status_code == 200
    obs_payload = list_obs.json()
    assert obs_payload["total"] == 1
    assert obs_payload["observations"][0]["value_text"] == "hello kernel"

    # 4) Seed a relation constraint so the triple is allowed
    with _session_for_api(db_session) as session:
        session.add(
            RelationConstraintModel(
                source_type="GENE",
                relation_type="ASSOCIATED_WITH",
                target_type="PHENOTYPE",
                is_allowed=True,
                requires_evidence=True,
            ),
        )
        session.commit()

    # 5) Create a relation
    rel_resp = test_client.post(
        f"/research-spaces/{space.id}/relations",
        headers=headers,
        json={
            "source_id": str(gene_id),
            "relation_type": "ASSOCIATED_WITH",
            "target_id": str(pheno_id),
            "confidence": 0.9,
            "evidence_summary": "Test evidence",
            "evidence_tier": "LITERATURE",
            "provenance_id": None,
        },
    )
    assert rel_resp.status_code == 201, rel_resp.text
    relation_id = UUID(rel_resp.json()["id"])

    list_rel = test_client.get(
        f"/research-spaces/{space.id}/relations",
        headers=headers,
    )
    assert list_rel.status_code == 200
    assert list_rel.json()["total"] == 1

    # 6) Graph export includes nodes + edge
    graph = test_client.get(
        f"/research-spaces/{space.id}/graph/export",
        headers=headers,
    )
    assert graph.status_code == 200
    graph_payload = graph.json()
    assert len(graph_payload["nodes"]) == 2
    assert len(graph_payload["edges"]) == 1

    # 7) Update curation status (space owner is allowed by current role policy)
    curate = test_client.put(
        f"/research-spaces/{space.id}/relations/{relation_id}",
        headers=headers,
        json={"curation_status": "APPROVED"},
    )
    assert curate.status_code == 200, curate.text
    assert curate.json()["curation_status"] == "APPROVED"


def test_kernel_ingest_endpoint_creates_entity_and_observation(
    test_client,
    db_session,
    admin_user,
    researcher_user,
    space,
):
    # 1) Create a variable and synonym mapping for ingestion
    resp = test_client.post(
        "/admin/dictionary/variables",
        headers=_auth_headers(admin_user),
        json={
            "id": "VAR_INGEST_NOTE",
            "canonical_name": "ingest_note",
            "display_name": "Ingest Note",
            "data_type": "STRING",
            "domain_context": "general",
            "sensitivity": "INTERNAL",
            "preferred_unit": None,
            "constraints": {},
            "description": "Variable used by ingest endpoint test",
        },
    )
    assert resp.status_code == 201, resp.text

    with _session_for_api(db_session) as session:
        session.add(
            VariableSynonymModel(
                variable_id="VAR_INGEST_NOTE",
                synonym="note",
                source="test",
            ),
        )
        session.commit()

    # 2) Ingest a record that contains an anchor + mapped field
    headers = _auth_headers(researcher_user)
    ingest = test_client.post(
        f"/research-spaces/{space.id}/ingest",
        headers=headers,
        json={
            "entity_type": "GENE",
            "records": [
                {
                    "source_id": "row-1",
                    "data": {"gene_symbol": "MED13", "note": "hello kernel ingest"},
                    "metadata": {},
                },
            ],
        },
    )
    assert ingest.status_code == 201, ingest.text
    payload = ingest.json()
    assert payload["success"] is True
    assert payload["entities_created"] == 1
    assert payload["observations_created"] == 1

    # 3) Verify the created entity is visible in the kernel entity API
    entities = test_client.get(
        f"/research-spaces/{space.id}/entities",
        headers=headers,
        params={"type": "GENE"},
    )
    assert entities.status_code == 200, entities.text
    assert entities.json()["total"] == 1

    # 4) Verify the observation is visible in the kernel observations API
    observations = test_client.get(
        f"/research-spaces/{space.id}/observations",
        headers=headers,
    )
    assert observations.status_code == 200, observations.text
    obs_payload = observations.json()
    assert obs_payload["total"] == 1
    assert obs_payload["observations"][0]["variable_id"] == "VAR_INGEST_NOTE"
    assert obs_payload["observations"][0]["value_text"] == "hello kernel ingest"
