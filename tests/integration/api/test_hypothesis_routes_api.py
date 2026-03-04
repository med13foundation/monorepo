"""Integration tests for research-space hypothesis endpoints."""

from __future__ import annotations

import os
from contextlib import contextmanager
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from src.application.agents.services.hypothesis_generation_service import (
    HypothesisGenerationResult,
)
from src.database import session as session_module
from src.domain.entities.kernel.relation_claims import KernelRelationClaim
from src.domain.entities.user import UserRole
from src.infrastructure.security.jwt_provider import JWTProvider
from src.main import create_app
from src.models.database.base import Base
from src.models.database.kernel.concepts import ConceptDecisionModel
from src.models.database.kernel.relation_claims import RelationClaimModel
from src.models.database.kernel.relations import RelationModel
from src.models.database.research_space import ResearchSpaceModel
from src.models.database.user import UserModel
from src.routes.research_spaces.hypothesis_routes import (
    get_hypothesis_generation_service_provider,
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
    suffix = uuid4().hex[:12]
    with _session_for_api(db_session) as session:
        user = UserModel(
            email=f"hypothesis-researcher-{suffix}@example.com",
            username=f"hypothesis-r-{suffix}",
            full_name="Hypothesis Researcher",
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
            slug=f"hypothesis-space-{suffix}",
            name="Hypothesis Space",
            description="Research space for hypothesis route tests",
            owner_id=researcher_user.id,
            status="active",
        )
        session.add(space)
        session.commit()
        session.refresh(space)
        session.expunge(space)
    return space


def test_manual_hypothesis_creation_and_listing(
    test_client: TestClient,
    db_session,
    researcher_user: UserModel,
    space: ResearchSpaceModel,
) -> None:
    headers = _auth_headers(researcher_user)
    seed_entity_id = uuid4()

    create_response = test_client.post(
        f"/research-spaces/{space.id}/hypotheses/manual",
        headers=headers,
        json={
            "statement": "MED13 mutations may influence autism through transcription dysregulation",
            "rationale": "Mediator complex perturbation can impact transcriptional regulation pathways.",
            "seed_entity_ids": [str(seed_entity_id)],
            "source_type": "manual",
        },
    )
    assert create_response.status_code == 200, create_response.text
    created = create_response.json()
    claim_id = created["claim_id"]
    assert created["origin"] == "manual"
    assert created["claim_status"] == "OPEN"

    list_response = test_client.get(
        f"/research-spaces/{space.id}/hypotheses",
        headers=headers,
    )
    assert list_response.status_code == 200, list_response.text
    payload = list_response.json()
    assert payload["total"] == 1
    assert payload["hypotheses"][0]["claim_id"] == claim_id

    with _session_for_api(db_session) as session:
        claim_row = session.scalar(
            select(RelationClaimModel).where(RelationClaimModel.id == UUID(claim_id)),
        )
        assert claim_row is not None
        assert claim_row.polarity == "HYPOTHESIS"
        assert claim_row.relation_type == "PROPOSES"
        assert claim_row.metadata_payload.get("workflow") == "hypothesis"
        concept_decision_id = claim_row.metadata_payload.get("concept_decision_id")
        if isinstance(concept_decision_id, str):
            decision = session.scalar(
                select(ConceptDecisionModel).where(
                    ConceptDecisionModel.id == UUID(concept_decision_id),
                ),
            )
            assert decision is not None
            assert decision.decision_payload.get("workflow") == "hypothesis"
        else:
            assert claim_row.metadata_payload.get("concept_decision_error") is not None


def test_generate_hypotheses_feature_flag_disabled(
    test_client: TestClient,
    researcher_user: UserModel,
    space: ResearchSpaceModel,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MED13_ENABLE_HYPOTHESIS_GENERATION", "0")
    headers = _auth_headers(researcher_user)

    response = test_client.post(
        f"/research-spaces/{space.id}/hypotheses/generate",
        headers=headers,
        json={
            "seed_entity_ids": None,
            "source_type": "pubmed",
            "max_depth": 2,
            "max_hypotheses": 20,
        },
    )

    assert response.status_code == 400, response.text
    payload = response.json()
    assert payload["detail"]["code"] == "FEATURE_DISABLED"


class _StubHypothesisGenerationService:
    def __init__(self, claim: KernelRelationClaim) -> None:
        self._claim = claim
        self.calls: list[dict[str, object]] = []

    async def generate_hypotheses(  # noqa: PLR0913
        self,
        *,
        research_space_id: str,
        seed_entity_ids: list[str] | None,
        source_type: str,
        relation_types: list[str] | None,
        max_depth: int,
        max_hypotheses: int,
        model_id: str | None,
    ) -> HypothesisGenerationResult:
        self.calls.append(
            {
                "research_space_id": research_space_id,
                "seed_entity_ids": seed_entity_ids,
                "source_type": source_type,
                "relation_types": relation_types,
                "max_depth": max_depth,
                "max_hypotheses": max_hypotheses,
                "model_id": model_id,
            },
        )
        return HypothesisGenerationResult(
            run_id=str(uuid4()),
            requested_seed_count=len(seed_entity_ids or []),
            used_seed_count=len(seed_entity_ids or []),
            candidates_seen=1,
            created_count=1,
            deduped_count=0,
            errors=(),
            hypotheses=(self._claim,),
        )


def _build_hypothesis_claim(
    *,
    claim_id: UUID,
    research_space_id: UUID,
) -> KernelRelationClaim:
    now = datetime.now(UTC)
    return KernelRelationClaim(
        id=claim_id,
        research_space_id=research_space_id,
        source_document_id=None,
        agent_run_id=None,
        source_type="GENE",
        relation_type="ASSOCIATED_WITH",
        target_type="PHENOTYPE",
        source_label="MED13",
        target_label="Autism",
        confidence=0.77,
        validation_state="ALLOWED",
        validation_reason=None,
        persistability="PERSISTABLE",
        claim_status="OPEN",
        polarity="HYPOTHESIS",
        claim_text="MED13 may influence autism progression.",
        claim_section=None,
        linked_relation_id=None,
        metadata_payload={
            "origin": "graph_agent",
            "seed_entity_id": str(uuid4()),
            "supporting_provenance_ids": [str(uuid4())],
        },
        triaged_by=None,
        triaged_at=None,
        created_at=now,
        updated_at=now,
    )


def test_generate_hypotheses_with_stub_has_no_canonical_relation_writes(
    db_session,
    researcher_user: UserModel,
    space: ResearchSpaceModel,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MED13_ENABLE_HYPOTHESIS_GENERATION", "1")
    app = create_app()

    stub_claim = _build_hypothesis_claim(
        claim_id=uuid4(),
        research_space_id=space.id,
    )
    service = _StubHypothesisGenerationService(stub_claim)
    app.dependency_overrides[get_hypothesis_generation_service_provider] = lambda: (
        lambda: service
    )
    client = TestClient(app)

    response = client.post(
        f"/research-spaces/{space.id}/hypotheses/generate",
        headers=_auth_headers(researcher_user),
        json={
            "seed_entity_ids": [str(uuid4())],
            "source_type": "pubmed",
            "max_depth": 2,
            "max_hypotheses": 20,
        },
    )

    app.dependency_overrides.clear()

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["created_count"] == 1
    assert payload["hypotheses"][0]["origin"] == "graph_agent"
    assert service.calls

    with _session_for_api(db_session) as session:
        relation_count = session.scalar(
            select(func.count()).select_from(RelationModel),
        )
    assert int(relation_count or 0) == 0


def test_manual_hypothesis_can_be_triaged_via_relation_claim_patch(
    test_client: TestClient,
    researcher_user: UserModel,
    space: ResearchSpaceModel,
) -> None:
    headers = _auth_headers(researcher_user)

    create_response = test_client.post(
        f"/research-spaces/{space.id}/hypotheses/manual",
        headers=headers,
        json={
            "statement": "MED13 variation may alter mediator regulation pathways.",
            "rationale": "Mediator dysregulation can explain downstream transcription effects.",
            "seed_entity_ids": [],
            "source_type": "manual",
        },
    )
    assert create_response.status_code == 200, create_response.text
    claim_id = create_response.json()["claim_id"]

    patch_response = test_client.patch(
        f"/research-spaces/{space.id}/relation-claims/{claim_id}",
        headers=headers,
        json={"claim_status": "NEEDS_MAPPING"},
    )
    assert patch_response.status_code == 200, patch_response.text
    assert patch_response.json()["claim_status"] == "NEEDS_MAPPING"
