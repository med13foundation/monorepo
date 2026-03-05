"""Integration tests for research-space hypothesis endpoints."""

from __future__ import annotations

import os
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from src.application.agents.services.hypothesis_generation_service import (
    HypothesisGenerationResult,
)
from src.database import session as session_module
from src.domain.entities.kernel.relation_claims import KernelRelationClaim
from src.domain.entities.user import UserRole
from src.infrastructure.security.jwt_provider import JWTProvider
from src.main import create_app
from src.models.database.base import Base
from src.models.database.kernel.claim_participants import ClaimParticipantModel
from src.models.database.kernel.claim_relations import ClaimRelationModel
from src.models.database.kernel.concepts import (
    ConceptDecisionModel,
    ConceptMemberModel,
    ConceptSetModel,
)
from src.models.database.kernel.dictionary import (
    DictionaryDomainContextModel,
    DictionaryEntityTypeModel,
)
from src.models.database.kernel.entities import EntityModel
from src.models.database.kernel.relation_claims import RelationClaimModel
from src.models.database.kernel.relations import RelationModel
from src.models.database.research_space import ResearchSpaceModel
from src.models.database.user import UserModel
from src.routes.research_spaces.hypothesis_routes import (
    get_hypothesis_generation_service_provider,
)
from tests.db_reset import reset_database

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


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


def _ensure_active_entity_type(session: Session, *, entity_type: str = "GENE") -> None:
    if session.get(DictionaryDomainContextModel, "general") is None:
        session.add(
            DictionaryDomainContextModel(
                id="general",
                display_name="General",
                description="General context for hypothesis API tests",
            ),
        )
        session.flush()

    existing = session.get(DictionaryEntityTypeModel, entity_type)
    if existing is None:
        session.add(
            DictionaryEntityTypeModel(
                id=entity_type,
                display_name=entity_type.replace("_", " ").title(),
                description=f"{entity_type} entity type",
                domain_context="general",
                created_by="manual:test",
                is_active=True,
                valid_to=None,
                review_status="ACTIVE",
                revocation_reason=None,
            ),
        )
        session.flush()
        return

    existing.is_active = True
    existing.valid_to = None
    existing.review_status = "ACTIVE"
    existing.revocation_reason = None
    session.flush()


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
    with _session_for_api(db_session) as session:
        _ensure_active_entity_type(session, entity_type="GENE")
        seed_entity = EntityModel(
            id=uuid4(),
            research_space_id=space.id,
            entity_type="GENE",
            display_label="MED13",
            metadata_payload={},
        )
        session.add(seed_entity)
        session.commit()
        seed_entity_id = seed_entity.id

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
        participant_rows = session.scalars(
            select(ClaimParticipantModel).where(
                ClaimParticipantModel.claim_id == UUID(claim_id),
            ),
        ).all()
        assert len(participant_rows) == 1
        assert str(participant_rows[0].entity_id) == str(seed_entity_id)
        assert participant_rows[0].role == "SUBJECT"
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


def test_claims_by_entity_route_uses_participants(
    test_client: TestClient,
    db_session,
    researcher_user: UserModel,
    space: ResearchSpaceModel,
) -> None:
    headers = _auth_headers(researcher_user)
    with _session_for_api(db_session) as session:
        _ensure_active_entity_type(session, entity_type="GENE")
        seed_entity = EntityModel(
            id=uuid4(),
            research_space_id=space.id,
            entity_type="GENE",
            display_label="MED13",
            metadata_payload={},
        )
        session.add(seed_entity)
        session.commit()
        seed_entity_id = seed_entity.id

    create_response = test_client.post(
        f"/research-spaces/{space.id}/hypotheses/manual",
        headers=headers,
        json={
            "statement": "MED13 influences mediator transcription pathways.",
            "rationale": "Mediator perturbation can alter disease-relevant expression.",
            "seed_entity_ids": [str(seed_entity_id)],
            "source_type": "manual",
        },
    )
    assert create_response.status_code == 200, create_response.text
    created_claim_id = create_response.json()["claim_id"]

    lookup_response = test_client.get(
        f"/research-spaces/{space.id}/claims/by-entity/{seed_entity_id}",
        headers=headers,
    )
    assert lookup_response.status_code == 200, lookup_response.text
    payload = lookup_response.json()
    assert payload["total"] >= 1
    claim_ids = {item["id"] for item in payload["claims"]}
    assert created_claim_id in claim_ids


def test_claim_relation_create_and_review_update(
    test_client: TestClient,
    db_session,
    researcher_user: UserModel,
    space: ResearchSpaceModel,
) -> None:
    headers = _auth_headers(researcher_user)

    first_response = test_client.post(
        f"/research-spaces/{space.id}/hypotheses/manual",
        headers=headers,
        json={
            "statement": "MED13 dysregulation contributes to transcription imbalance.",
            "rationale": "Gene-level mediator disruption can drive downstream effects.",
            "seed_entity_ids": [],
            "source_type": "manual",
        },
    )
    assert first_response.status_code == 200, first_response.text
    source_claim_id = first_response.json()["claim_id"]

    second_response = test_client.post(
        f"/research-spaces/{space.id}/hypotheses/manual",
        headers=headers,
        json={
            "statement": "Transcription imbalance contributes to autism pathology.",
            "rationale": "Disease phenotype aligns with transcriptional disruptions.",
            "seed_entity_ids": [],
            "source_type": "manual",
        },
    )
    assert second_response.status_code == 200, second_response.text
    target_claim_id = second_response.json()["claim_id"]

    create_relation_response = test_client.post(
        f"/research-spaces/{space.id}/claim-relations",
        headers=headers,
        json={
            "source_claim_id": source_claim_id,
            "target_claim_id": target_claim_id,
            "relation_type": "SUPPORTS",
            "confidence": 0.74,
            "review_status": "PROPOSED",
            "metadata": {"origin": "manual_test"},
        },
    )
    assert create_relation_response.status_code == 200, create_relation_response.text
    relation_payload = create_relation_response.json()
    relation_id = relation_payload["id"]
    assert relation_payload["review_status"] == "PROPOSED"
    assert relation_payload["relation_type"] == "SUPPORTS"

    duplicate_relation_response = test_client.post(
        f"/research-spaces/{space.id}/claim-relations",
        headers=headers,
        json={
            "source_claim_id": source_claim_id,
            "target_claim_id": target_claim_id,
            "relation_type": "SUPPORTS",
            "confidence": 0.74,
            "review_status": "PROPOSED",
            "metadata": {"origin": "manual_test_duplicate"},
        },
    )
    assert (
        duplicate_relation_response.status_code == 409
    ), duplicate_relation_response.text

    patch_response = test_client.patch(
        f"/research-spaces/{space.id}/claim-relations/{relation_id}",
        headers=headers,
        json={"review_status": "ACCEPTED"},
    )
    assert patch_response.status_code == 200, patch_response.text
    assert patch_response.json()["review_status"] == "ACCEPTED"

    with _session_for_api(db_session) as session:
        row = session.scalar(
            select(ClaimRelationModel).where(
                ClaimRelationModel.id == UUID(relation_id),
            ),
        )
        assert row is not None
        assert row.review_status == "ACCEPTED"


def test_claim_participant_coverage_and_backfill(
    test_client: TestClient,
    db_session,
    researcher_user: UserModel,
    space: ResearchSpaceModel,
) -> None:
    headers = _auth_headers(researcher_user)

    with _session_for_api(db_session) as session:
        claim = RelationClaimModel(
            id=uuid4(),
            research_space_id=space.id,
            source_document_id=None,
            agent_run_id=None,
            source_type="GENE",
            relation_type="ASSOCIATED_WITH",
            target_type="PHENOTYPE",
            source_label="MED13",
            target_label="Autism",
            confidence=0.71,
            validation_state="ALLOWED",
            validation_reason=None,
            persistability="PERSISTABLE",
            claim_status="OPEN",
            polarity="HYPOTHESIS",
            claim_text="MED13 may influence autism.",
            claim_section=None,
            linked_relation_id=None,
            metadata_payload={"origin": "manual"},
        )
        session.add(claim)
        session.commit()
        claim_id = claim.id

    pre_coverage_response = test_client.get(
        f"/research-spaces/{space.id}/claim-participants/coverage",
        headers=headers,
        params={"limit": 200, "offset": 0},
    )
    assert pre_coverage_response.status_code == 200, pre_coverage_response.text
    pre_coverage = pre_coverage_response.json()
    assert pre_coverage["total_claims"] >= 1
    assert pre_coverage["claims_with_subject"] == 0
    assert pre_coverage["claims_with_object"] == 0

    dry_run_response = test_client.post(
        f"/research-spaces/{space.id}/claim-participants/backfill",
        headers=headers,
        json={"dry_run": True, "limit": 200, "offset": 0},
    )
    assert dry_run_response.status_code == 200, dry_run_response.text
    dry_run_payload = dry_run_response.json()
    assert dry_run_payload["created_participants"] >= 2
    assert dry_run_payload["dry_run"] is True

    run_response = test_client.post(
        f"/research-spaces/{space.id}/claim-participants/backfill",
        headers=headers,
        json={"dry_run": False, "limit": 200, "offset": 0},
    )
    assert run_response.status_code == 200, run_response.text
    run_payload = run_response.json()
    assert run_payload["created_participants"] >= 2
    assert run_payload["dry_run"] is False

    with _session_for_api(db_session) as session:
        participants = session.scalars(
            select(ClaimParticipantModel).where(
                ClaimParticipantModel.claim_id == claim_id,
            ),
        ).all()
        roles = {participant.role for participant in participants}
        assert "SUBJECT" in roles
        assert "OBJECT" in roles

    post_coverage_response = test_client.get(
        f"/research-spaces/{space.id}/claim-participants/coverage",
        headers=headers,
        params={"limit": 200, "offset": 0},
    )
    assert post_coverage_response.status_code == 200, post_coverage_response.text
    post_coverage = post_coverage_response.json()
    assert post_coverage["claims_with_subject"] >= 1
    assert post_coverage["claims_with_object"] >= 1


def test_claim_participant_backfill_maps_concept_member_to_entity(
    test_client: TestClient,
    db_session,
    researcher_user: UserModel,
    space: ResearchSpaceModel,
) -> None:
    headers = _auth_headers(researcher_user)

    with _session_for_api(db_session) as session:
        _ensure_active_entity_type(session, entity_type="GENE")
        mapped_entity = EntityModel(
            id=uuid4(),
            research_space_id=space.id,
            entity_type="GENE",
            display_label="MED13",
            metadata_payload={},
        )
        concept_set = ConceptSetModel(
            id=uuid4(),
            research_space_id=space.id,
            name="Extraction Concepts",
            slug=f"extraction-{uuid4().hex[:8]}",
            domain_context="general",
            created_by="manual:test",
            review_status="ACTIVE",
            is_active=True,
            valid_to=None,
        )
        session.add(mapped_entity)
        session.add(concept_set)
        session.flush()

        source_member = ConceptMemberModel(
            id=uuid4(),
            concept_set_id=concept_set.id,
            research_space_id=space.id,
            domain_context="general",
            dictionary_dimension=None,
            dictionary_entry_id=None,
            canonical_label="MED13",
            normalized_label="med13",
            sense_key="gene",
            is_provisional=False,
            metadata_payload={"entity_id": str(mapped_entity.id)},
            created_by="manual:test",
            review_status="ACTIVE",
            is_active=True,
            valid_to=None,
        )
        target_member = ConceptMemberModel(
            id=uuid4(),
            concept_set_id=concept_set.id,
            research_space_id=space.id,
            domain_context="general",
            dictionary_dimension=None,
            dictionary_entry_id=None,
            canonical_label="Autism",
            normalized_label="autism",
            sense_key="disease",
            is_provisional=False,
            metadata_payload={},
            created_by="manual:test",
            review_status="ACTIVE",
            is_active=True,
            valid_to=None,
        )
        claim = RelationClaimModel(
            id=uuid4(),
            research_space_id=space.id,
            source_document_id=None,
            agent_run_id=None,
            source_type="GENE",
            relation_type="ASSOCIATED_WITH",
            target_type="DISEASE",
            source_label=None,
            target_label=None,
            confidence=0.72,
            validation_state="ALLOWED",
            validation_reason=None,
            persistability="PERSISTABLE",
            claim_status="OPEN",
            polarity="HYPOTHESIS",
            claim_text="MED13 may influence autism through transcription dysregulation.",
            claim_section=None,
            linked_relation_id=None,
            metadata_payload={
                "origin": "graph_agent",
                "concept_refs": {
                    "concept_set_id": str(concept_set.id),
                    "source_member_id": str(source_member.id),
                    "target_member_id": str(target_member.id),
                },
            },
        )

        session.add(source_member)
        session.add(target_member)
        session.add(claim)
        session.commit()
        claim_id = claim.id
        mapped_entity_id = mapped_entity.id

    run_response = test_client.post(
        f"/research-spaces/{space.id}/claim-participants/backfill",
        headers=headers,
        json={"dry_run": False, "limit": 200, "offset": 0},
    )
    assert run_response.status_code == 200, run_response.text

    with _session_for_api(db_session) as session:
        participants = session.scalars(
            select(ClaimParticipantModel).where(
                ClaimParticipantModel.claim_id == claim_id,
            ),
        ).all()
        by_role = {participant.role: participant for participant in participants}
        assert "SUBJECT" in by_role
        assert by_role["SUBJECT"].entity_id == mapped_entity_id
        assert by_role["SUBJECT"].label == "MED13"
        assert "OBJECT" in by_role
        assert by_role["OBJECT"].entity_id is None
        assert by_role["OBJECT"].label == "Autism"


def test_claim_participant_cross_space_entity_fk_enforced(
    db_session,
    researcher_user: UserModel,
    space: ResearchSpaceModel,
) -> None:
    if not _using_postgres():
        pytest.skip("Cross-space composite FK enforcement is validated on PostgreSQL.")

    with _session_for_api(db_session) as session:
        _ensure_active_entity_type(session, entity_type="GENE")

        other_space = ResearchSpaceModel(
            slug=f"hypothesis-space-other-{uuid4().hex[:16]}",
            name="Hypothesis Other Space",
            description="Cross-space FK enforcement test space",
            owner_id=researcher_user.id,
            status="active",
        )
        session.add(other_space)
        session.flush()

        claim = RelationClaimModel(
            id=uuid4(),
            research_space_id=space.id,
            source_document_id=None,
            agent_run_id=None,
            source_type="GENE",
            relation_type="ASSOCIATED_WITH",
            target_type="PHENOTYPE",
            source_label="MED13",
            target_label="Autism",
            confidence=0.7,
            validation_state="ALLOWED",
            validation_reason=None,
            persistability="PERSISTABLE",
            claim_status="OPEN",
            polarity="HYPOTHESIS",
            claim_text="Cross-space participant FK enforcement.",
            claim_section=None,
            linked_relation_id=None,
            metadata_payload={},
        )
        foreign_entity = EntityModel(
            id=uuid4(),
            research_space_id=other_space.id,
            entity_type="GENE",
            display_label="MED13",
            metadata_payload={},
        )
        session.add(claim)
        session.add(foreign_entity)
        session.commit()

        participant = ClaimParticipantModel(
            id=uuid4(),
            claim_id=claim.id,
            research_space_id=space.id,
            label="MED13",
            entity_id=foreign_entity.id,
            role="SUBJECT",
            position=0,
            qualifiers={},
        )
        session.add(participant)

        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()
