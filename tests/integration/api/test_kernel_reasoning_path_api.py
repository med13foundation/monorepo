"""Integration tests for derived reasoning-path API routes."""

from __future__ import annotations

import os
from contextlib import contextmanager
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from src.database import session as session_module
from src.database.seeds.seeder import (
    seed_entity_resolution_policies,
    seed_relation_constraints,
)
from src.domain.entities.user import UserRole
from src.infrastructure.security.jwt_provider import JWTProvider
from src.main import create_app
from src.models.database.base import Base
from src.models.database.kernel.claim_evidence import ClaimEvidenceModel
from src.models.database.kernel.claim_participants import ClaimParticipantModel
from src.models.database.kernel.claim_relations import ClaimRelationModel
from src.models.database.kernel.dictionary import (
    DictionaryDomainContextModel,
    DictionaryEntityTypeModel,
    DictionaryRelationTypeModel,
    RelationConstraintModel,
)
from src.models.database.kernel.entities import EntityModel
from src.models.database.kernel.reasoning_paths import (
    ReasoningPathModel,
    ReasoningPathStepModel,
)
from src.models.database.kernel.relation_claims import RelationClaimModel
from src.models.database.kernel.relation_projection_sources import (
    RelationProjectionSourceModel,
)
from src.models.database.kernel.relations import RelationEvidenceModel, RelationModel
from src.models.database.research_space import ResearchSpaceModel
from src.models.database.user import UserModel
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


def _ensure_active_entity_type(session, *, entity_type: str) -> None:
    if session.get(DictionaryDomainContextModel, "general") is None:
        session.add(
            DictionaryDomainContextModel(
                id="general",
                display_name="General",
                description="General context for reasoning path API tests",
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


def _ensure_active_relation_type(session, *, relation_type: str) -> None:
    if session.get(DictionaryDomainContextModel, "general") is None:
        session.add(
            DictionaryDomainContextModel(
                id="general",
                display_name="General",
                description="General context for reasoning path API tests",
            ),
        )
        session.flush()

    existing = session.get(DictionaryRelationTypeModel, relation_type)
    if existing is None:
        session.add(
            DictionaryRelationTypeModel(
                id=relation_type,
                display_name=relation_type.replace("_", " ").title(),
                description=f"{relation_type} relation type",
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


def _ensure_allowed_relation_constraint(
    session,
    *,
    source_type: str,
    relation_type: str,
    target_type: str,
) -> None:
    existing = session.execute(
        select(RelationConstraintModel).where(
            RelationConstraintModel.source_type == source_type,
            RelationConstraintModel.relation_type == relation_type,
            RelationConstraintModel.target_type == target_type,
        ),
    ).scalar_one_or_none()
    if existing is None:
        session.add(
            RelationConstraintModel(
                source_type=source_type,
                relation_type=relation_type,
                target_type=target_type,
                is_allowed=True,
                requires_evidence=False,
                created_by="manual:test",
                is_active=True,
                review_status="ACTIVE",
            ),
        )
        session.flush()
        return

    existing.is_allowed = True
    existing.requires_evidence = False
    existing.is_active = True
    existing.review_status = "ACTIVE"
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
            email=f"reasoning-researcher-{suffix}@example.com",
            username=f"reasoning-r-{suffix}",
            full_name="Reasoning Researcher",
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
            slug=f"reasoning-space-{suffix}",
            name="Reasoning Space",
            description="Research space for reasoning path API tests",
            owner_id=researcher_user.id,
            status="active",
        )
        session.add(space)
        session.commit()
        session.refresh(space)
        session.expunge(space)
    return space


def test_reasoning_path_list_and_detail_routes(
    test_client: TestClient,
    db_session,
    researcher_user: UserModel,
    space: ResearchSpaceModel,
) -> None:
    headers = _auth_headers(researcher_user)
    path_id = uuid4()
    start_entity_id = uuid4()
    mid_entity_id = uuid4()
    end_entity_id = uuid4()
    root_claim_id = uuid4()
    final_claim_id = uuid4()
    claim_relation_id = uuid4()
    canonical_relation_id = uuid4()

    with _session_for_api(db_session) as session:
        seed_entity_resolution_policies(session)
        seed_relation_constraints(session)
        _ensure_active_entity_type(session, entity_type="GENE")
        _ensure_active_entity_type(session, entity_type="COMPLEX")
        _ensure_active_entity_type(session, entity_type="PHENOTYPE")
        _ensure_active_relation_type(session, relation_type="PART_OF")
        _ensure_allowed_relation_constraint(
            session,
            source_type="GENE",
            relation_type="PART_OF",
            target_type="COMPLEX",
        )
        session.add_all(
            [
                EntityModel(
                    id=start_entity_id,
                    research_space_id=space.id,
                    entity_type="GENE",
                    display_label="MED13",
                    metadata_payload={},
                ),
                EntityModel(
                    id=mid_entity_id,
                    research_space_id=space.id,
                    entity_type="COMPLEX",
                    display_label="Mediator complex",
                    metadata_payload={},
                ),
                EntityModel(
                    id=end_entity_id,
                    research_space_id=space.id,
                    entity_type="PHENOTYPE",
                    display_label="Speech delay",
                    metadata_payload={},
                ),
            ],
        )
        session.flush()
        session.add(
            RelationModel(
                id=canonical_relation_id,
                research_space_id=space.id,
                source_id=start_entity_id,
                relation_type="PART_OF",
                target_id=mid_entity_id,
                aggregate_confidence=0.88,
                source_count=1,
                highest_evidence_tier="LITERATURE",
                curation_status="DRAFT",
                provenance_id=None,
                reviewed_by=None,
                reviewed_at=None,
            ),
        )
        session.flush()

        session.add_all(
            [
                RelationClaimModel(
                    id=root_claim_id,
                    research_space_id=space.id,
                    source_document_id=None,
                    agent_run_id=None,
                    source_type="GENE",
                    relation_type="PART_OF",
                    target_type="COMPLEX",
                    source_label="MED13",
                    target_label="Mediator complex",
                    confidence=0.88,
                    validation_state="ALLOWED",
                    validation_reason=None,
                    persistability="PERSISTABLE",
                    claim_status="RESOLVED",
                    polarity="SUPPORT",
                    claim_text="MED13 is part of mediator complex.",
                    claim_section=None,
                    linked_relation_id=canonical_relation_id,
                    metadata_payload={},
                    triaged_by=None,
                    triaged_at=None,
                ),
                RelationClaimModel(
                    id=final_claim_id,
                    research_space_id=space.id,
                    source_document_id=None,
                    agent_run_id=None,
                    source_type="PROCESS",
                    relation_type="ASSOCIATED_WITH",
                    target_type="PHENOTYPE",
                    source_label="Transcription dysregulation",
                    target_label="Speech delay",
                    confidence=0.81,
                    validation_state="ALLOWED",
                    validation_reason=None,
                    persistability="PERSISTABLE",
                    claim_status="RESOLVED",
                    polarity="SUPPORT",
                    claim_text="Transcription dysregulation is associated with speech delay.",
                    claim_section=None,
                    linked_relation_id=None,
                    metadata_payload={},
                    triaged_by=None,
                    triaged_at=None,
                ),
            ],
        )
        session.flush()

        session.add_all(
            [
                ClaimParticipantModel(
                    claim_id=root_claim_id,
                    research_space_id=space.id,
                    label="MED13",
                    entity_id=start_entity_id,
                    role="SUBJECT",
                    position=0,
                    qualifiers={},
                ),
                ClaimParticipantModel(
                    claim_id=root_claim_id,
                    research_space_id=space.id,
                    label="Mediator complex",
                    entity_id=mid_entity_id,
                    role="OBJECT",
                    position=1,
                    qualifiers={},
                ),
                ClaimParticipantModel(
                    claim_id=final_claim_id,
                    research_space_id=space.id,
                    label="Transcription dysregulation",
                    entity_id=mid_entity_id,
                    role="SUBJECT",
                    position=0,
                    qualifiers={},
                ),
                ClaimParticipantModel(
                    claim_id=final_claim_id,
                    research_space_id=space.id,
                    label="Speech delay",
                    entity_id=end_entity_id,
                    role="OBJECT",
                    position=1,
                    qualifiers={},
                ),
            ],
        )
        session.add_all(
            [
                ClaimEvidenceModel(
                    claim_id=root_claim_id,
                    source_document_id=None,
                    agent_run_id="run-root",
                    sentence="MED13 is a mediator complex subunit.",
                    sentence_source="verbatim_span",
                    sentence_confidence="high",
                    sentence_rationale=None,
                    figure_reference=None,
                    table_reference=None,
                    confidence=0.9,
                    metadata_payload={},
                ),
                ClaimEvidenceModel(
                    claim_id=final_claim_id,
                    source_document_id=None,
                    agent_run_id="run-leaf",
                    sentence="Transcription dysregulation correlates with speech delay.",
                    sentence_source="verbatim_span",
                    sentence_confidence="high",
                    sentence_rationale=None,
                    figure_reference=None,
                    table_reference=None,
                    confidence=0.84,
                    metadata_payload={},
                ),
            ],
        )
        session.add(
            ClaimRelationModel(
                id=claim_relation_id,
                research_space_id=space.id,
                source_claim_id=root_claim_id,
                target_claim_id=final_claim_id,
                relation_type="CAUSES",
                agent_run_id=None,
                source_document_id=None,
                confidence=0.73,
                review_status="ACCEPTED",
                evidence_summary="Mechanistic support",
                metadata_payload={},
            ),
        )
        session.add(
            RelationProjectionSourceModel(
                research_space_id=space.id,
                relation_id=canonical_relation_id,
                claim_id=root_claim_id,
                projection_origin="CLAIM_RESOLUTION",
                source_document_id=None,
                agent_run_id=None,
                metadata_payload={},
            ),
        )
        session.add(
            RelationEvidenceModel(
                relation_id=canonical_relation_id,
                provenance_id=None,
                evidence_summary="Derived evidence cache",
                evidence_tier="LITERATURE",
                confidence=0.88,
                source_document_id=None,
                agent_run_id="evidence-cache",
                evidence_sentence="MED13 is a mediator complex subunit.",
                evidence_sentence_source="derived_claim_evidence",
                evidence_sentence_confidence="high",
                evidence_sentence_rationale=None,
            ),
        )
        session.add(
            ReasoningPathModel(
                id=path_id,
                research_space_id=space.id,
                path_kind="MECHANISM",
                status="ACTIVE",
                start_entity_id=start_entity_id,
                end_entity_id=end_entity_id,
                root_claim_id=root_claim_id,
                path_length=1,
                confidence=0.73,
                path_signature_hash="0123456789abcdef0123456789abcdef",
                generated_by="test",
                metadata_payload={
                    "terminal_relation_type": "ASSOCIATED_WITH",
                    "supporting_claim_ids": [
                        str(root_claim_id),
                        str(final_claim_id),
                    ],
                },
            ),
        )
        session.flush()
        session.add(
            ReasoningPathStepModel(
                path_id=path_id,
                step_index=0,
                source_claim_id=root_claim_id,
                target_claim_id=final_claim_id,
                claim_relation_id=claim_relation_id,
                canonical_relation_id=canonical_relation_id,
                metadata_payload={"relation_type": "CAUSES", "confidence": 0.73},
            ),
        )
        session.commit()

    list_response = test_client.get(
        f"/research-spaces/{space.id}/graph/reasoning-paths",
        headers=headers,
        params={"start_entity_id": str(start_entity_id)},
    )
    assert list_response.status_code == 200, list_response.text
    list_payload = list_response.json()
    assert list_payload["total"] == 1
    assert list_payload["paths"][0]["id"] == str(path_id)
    assert list_payload["paths"][0]["status"] == "ACTIVE"

    detail_response = test_client.get(
        f"/research-spaces/{space.id}/graph/reasoning-paths/{path_id}",
        headers=headers,
    )
    assert detail_response.status_code == 200, detail_response.text
    detail_payload = detail_response.json()
    assert detail_payload["path"]["id"] == str(path_id)
    assert len(detail_payload["steps"]) == 1
    assert len(detail_payload["claims"]) == 2
    assert len(detail_payload["claim_relations"]) == 1
    assert len(detail_payload["canonical_relations"]) == 1
    assert len(detail_payload["evidence"]) == 2
    assert detail_payload["steps"][0]["claim_relation_id"] == str(claim_relation_id)
