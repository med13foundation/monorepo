"""Integration tests for graph domain views and mechanism-chain routes."""

from __future__ import annotations

import os
from contextlib import contextmanager
from uuid import UUID, uuid4

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
from src.models.database.kernel.entities import EntityModel
from src.models.database.kernel.relation_claims import RelationClaimModel
from src.models.database.kernel.relation_projection_sources import (
    RelationProjectionSourceModel,
)
from src.models.database.kernel.relations import RelationEvidenceModel, RelationModel
from src.models.database.research_space import ResearchSpaceModel
from src.models.database.source_document import (
    DocumentExtractionStatusEnum,
    DocumentFormatEnum,
    EnrichmentStatusEnum,
    SourceDocumentModel,
)
from src.models.database.user import UserModel
from src.models.database.user_data_source import (
    SourceStatusEnum,
    SourceTypeEnum,
    UserDataSourceModel,
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


def _seed_kernel_dictionary(session) -> None:
    seed_entity_resolution_policies(session)
    seed_relation_constraints(session)
    session.commit()


def _create_entity(
    *,
    session,
    space_id: UUID,
    entity_type: str,
    display_label: str,
) -> UUID:
    entity = EntityModel(
        id=uuid4(),
        research_space_id=space_id,
        entity_type=entity_type,
        display_label=display_label,
        metadata_payload={},
    )
    session.add(entity)
    session.commit()
    return entity.id


def _create_admin_user(session) -> UserModel:
    suffix = uuid4().hex[:12]
    user = UserModel(
        email=f"graph-admin-{suffix}@example.com",
        username=f"graph-admin-{suffix}",
        full_name="Graph Admin",
        hashed_password="hashed_password",
        role=UserRole.ADMIN.value,
        status="active",
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    session.expunge(user)
    return user


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
            email=f"graph-researcher-{suffix}@example.com",
            username=f"graph-r-{suffix}",
            full_name="Graph Researcher",
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
            slug=f"graph-view-space-{suffix}",
            name="Graph View Space",
            description="Research space for graph view tests",
            owner_id=researcher_user.id,
            status="active",
        )
        session.add(space)
        session.commit()
        session.refresh(space)
        session.expunge(space)
    return space


def test_claim_mechanism_chain_route_returns_mechanistic_claim_graph(
    test_client: TestClient,
    db_session,
    researcher_user: UserModel,
    space: ResearchSpaceModel,
) -> None:
    headers = _auth_headers(researcher_user)

    with _session_for_api(db_session) as session:
        _seed_kernel_dictionary(session)
        seed_entity_id = _create_entity(
            session=session,
            space_id=space.id,
            entity_type="GENE",
            display_label="MED13",
        )

    root_response = test_client.post(
        f"/research-spaces/{space.id}/hypotheses/manual",
        headers=headers,
        json={
            "statement": "MED13 mutation disrupts mediator complex function.",
            "rationale": "MED13 is a mediator-complex component.",
            "seed_entity_ids": [str(seed_entity_id)],
            "source_type": "manual",
        },
    )
    assert root_response.status_code == 200, root_response.text
    root_claim_id = UUID(root_response.json()["claim_id"])

    middle_response = test_client.post(
        f"/research-spaces/{space.id}/hypotheses/manual",
        headers=headers,
        json={
            "statement": "Mediator complex dysfunction perturbs transcription.",
            "rationale": "Mediator regulates transcriptional control.",
            "seed_entity_ids": [],
            "source_type": "manual",
        },
    )
    assert middle_response.status_code == 200, middle_response.text
    middle_claim_id = UUID(middle_response.json()["claim_id"])

    leaf_response = test_client.post(
        f"/research-spaces/{space.id}/hypotheses/manual",
        headers=headers,
        json={
            "statement": "Transcription dysregulation contributes to neurodevelopmental disease.",
            "rationale": "Neurodevelopment is transcription-sensitive.",
            "seed_entity_ids": [],
            "source_type": "manual",
        },
    )
    assert leaf_response.status_code == 200, leaf_response.text
    leaf_claim_id = UUID(leaf_response.json()["claim_id"])

    edge_one = test_client.post(
        f"/research-spaces/{space.id}/claim-relations",
        headers=headers,
        json={
            "source_claim_id": str(root_claim_id),
            "target_claim_id": str(middle_claim_id),
            "relation_type": "CAUSES",
            "confidence": 0.82,
            "review_status": "ACCEPTED",
            "metadata": {"origin": "mechanism_test"},
        },
    )
    assert edge_one.status_code == 200, edge_one.text

    edge_two = test_client.post(
        f"/research-spaces/{space.id}/claim-relations",
        headers=headers,
        json={
            "source_claim_id": str(middle_claim_id),
            "target_claim_id": str(leaf_claim_id),
            "relation_type": "UPSTREAM_OF",
            "confidence": 0.79,
            "review_status": "ACCEPTED",
            "metadata": {"origin": "mechanism_test"},
        },
    )
    assert edge_two.status_code == 200, edge_two.text

    with _session_for_api(db_session) as session:
        session.add(
            ClaimEvidenceModel(
                claim_id=root_claim_id,
                source_document_id=None,
                agent_run_id="run-mechanism-root",
                sentence="MED13 perturbation alters mediator complex stability.",
                sentence_source="artana_generated",
                sentence_confidence="high",
                sentence_rationale="Manual mechanism-chain test evidence",
                figure_reference=None,
                table_reference=None,
                confidence=0.88,
                metadata_payload={},
            ),
        )
        session.add(
            ClaimEvidenceModel(
                claim_id=middle_claim_id,
                source_document_id=None,
                agent_run_id="run-mechanism-middle",
                sentence="Mediator dysfunction can drive transcriptional imbalance.",
                sentence_source="artana_generated",
                sentence_confidence="medium",
                sentence_rationale="Manual mechanism-chain test evidence",
                figure_reference=None,
                table_reference=None,
                confidence=0.75,
                metadata_payload={},
            ),
        )
        session.commit()

    response = test_client.get(
        f"/research-spaces/{space.id}/claims/{root_claim_id}/mechanism-chain",
        headers=headers,
        params={"max_depth": 2},
    )
    assert response.status_code == 200, response.text
    payload = response.json()

    assert payload["root_claim"]["id"] == str(root_claim_id)
    assert payload["max_depth"] == 2
    claim_ids = {item["id"] for item in payload["claims"]}
    assert claim_ids == {
        str(root_claim_id),
        str(middle_claim_id),
        str(leaf_claim_id),
    }
    assert payload["counts"]["claim_relations"] == 2
    assert payload["counts"]["participants"] >= 1
    assert payload["counts"]["evidence"] == 2


def test_gene_graph_view_route_returns_claims_relations_and_evidence(
    test_client: TestClient,
    db_session,
    researcher_user: UserModel,
    space: ResearchSpaceModel,
) -> None:
    researcher_headers = _auth_headers(researcher_user)

    with _session_for_api(db_session) as session:
        _seed_kernel_dictionary(session)
        source_id = _create_entity(
            session=session,
            space_id=space.id,
            entity_type="GENE",
            display_label="MED13",
        )
        target_id = _create_entity(
            session=session,
            space_id=space.id,
            entity_type="PHENOTYPE",
            display_label="Developmental delay",
        )
        admin_user = _create_admin_user(session)

    admin_headers = _auth_headers(admin_user)
    relation_response = test_client.post(
        f"/research-spaces/{space.id}/relations",
        headers=admin_headers,
        json={
            "source_id": str(source_id),
            "relation_type": "ASSOCIATED_WITH",
            "target_id": str(target_id),
            "confidence": 0.91,
            "evidence_summary": "Curated support evidence",
            "evidence_sentence": "MED13 is associated with developmental delay.",
            "evidence_tier": "LITERATURE",
            "provenance_id": None,
        },
    )
    assert relation_response.status_code == 201, relation_response.text
    relation_id = UUID(relation_response.json()["id"])

    with _session_for_api(db_session) as session:
        support_claim = session.scalar(
            select(RelationClaimModel).where(
                RelationClaimModel.linked_relation_id == relation_id,
            ),
        )
        assert support_claim is not None
        support_claim_id = support_claim.id

    hypothesis_response = test_client.post(
        f"/research-spaces/{space.id}/hypotheses/manual",
        headers=researcher_headers,
        json={
            "statement": "MED13-associated transcription changes may worsen developmental delay.",
            "rationale": "Mediator disruption could amplify phenotype severity.",
            "seed_entity_ids": [str(source_id)],
            "source_type": "manual",
        },
    )
    assert hypothesis_response.status_code == 200, hypothesis_response.text
    hypothesis_claim_id = hypothesis_response.json()["claim_id"]

    claim_relation_response = test_client.post(
        f"/research-spaces/{space.id}/claim-relations",
        headers=researcher_headers,
        json={
            "source_claim_id": str(support_claim_id),
            "target_claim_id": hypothesis_claim_id,
            "relation_type": "SUPPORTS",
            "confidence": 0.67,
            "review_status": "ACCEPTED",
            "metadata": {"origin": "gene_view_test"},
        },
    )
    assert claim_relation_response.status_code == 200, claim_relation_response.text

    response = test_client.get(
        f"/research-spaces/{space.id}/graph/views/gene/{source_id}",
        headers=researcher_headers,
        params={"claim_limit": 25, "relation_limit": 25},
    )
    assert response.status_code == 200, response.text
    payload = response.json()

    assert payload["view_type"] == "gene"
    assert payload["entity"]["id"] == str(source_id)
    assert payload["counts"]["canonical_relations"] == 1
    assert payload["counts"]["claims"] >= 2
    assert payload["counts"]["claim_relations"] == 1
    assert payload["counts"]["participants"] >= 3
    assert payload["counts"]["evidence"] >= 1
    assert payload["canonical_relations"][0]["id"] == str(relation_id)


def test_paper_graph_view_route_returns_claim_backed_projection_bundle(
    test_client: TestClient,
    db_session,
    researcher_user: UserModel,
    space: ResearchSpaceModel,
) -> None:
    headers = _auth_headers(researcher_user)
    source_document_uuid = uuid4()
    relation_id = uuid4()
    claim_id = uuid4()

    with _session_for_api(db_session) as session:
        _seed_kernel_dictionary(session)
        source_id = _create_entity(
            session=session,
            space_id=space.id,
            entity_type="GENE",
            display_label="MED13",
        )
        target_id = _create_entity(
            session=session,
            space_id=space.id,
            entity_type="PHENOTYPE",
            display_label="Cardiomyopathy",
        )
        data_source = UserDataSourceModel(
            id=str(uuid4()),
            owner_id=str(researcher_user.id),
            research_space_id=str(space.id),
            name="PubMed Import",
            description="Test source",
            source_type=SourceTypeEnum.PUBMED,
            template_id=None,
            configuration={},
            status=SourceStatusEnum.ACTIVE,
            ingestion_schedule={},
            quality_metrics={},
            last_ingested_at=None,
            tags=[],
            version="1.0",
        )
        document = SourceDocumentModel(
            id=str(source_document_uuid),
            research_space_id=str(space.id),
            source_id=data_source.id,
            ingestion_job_id=None,
            external_record_id="PMID:123456",
            source_type=SourceTypeEnum.PUBMED.value,
            document_format=DocumentFormatEnum.TEXT.value,
            raw_storage_key=None,
            enriched_storage_key=None,
            content_hash=None,
            content_length_chars=1024,
            enrichment_status=EnrichmentStatusEnum.ENRICHED.value,
            enrichment_method=None,
            enrichment_agent_run_id=None,
            extraction_status=DocumentExtractionStatusEnum.EXTRACTED.value,
            extraction_agent_run_id="run-paper-view",
            metadata_payload={"title": "MED13 and cardiomyopathy"},
        )
        relation = RelationModel(
            id=relation_id,
            research_space_id=space.id,
            source_id=source_id,
            relation_type="ASSOCIATED_WITH",
            target_id=target_id,
            aggregate_confidence=0.83,
            source_count=1,
            highest_evidence_tier="LITERATURE",
            curation_status="APPROVED",
            provenance_id=None,
        )
        claim = RelationClaimModel(
            id=claim_id,
            research_space_id=space.id,
            source_document_id=source_document_uuid,
            agent_run_id="run-paper-view",
            source_type="GENE",
            relation_type="ASSOCIATED_WITH",
            target_type="PHENOTYPE",
            source_label="MED13",
            target_label="Cardiomyopathy",
            confidence=0.83,
            validation_state="ALLOWED",
            validation_reason=None,
            persistability="PERSISTABLE",
            claim_status="RESOLVED",
            polarity="SUPPORT",
            claim_text="MED13 variants were associated with cardiomyopathy.",
            claim_section="results",
            linked_relation_id=relation_id,
            metadata_payload={"origin": "paper_view_test"},
        )
        projection_source = RelationProjectionSourceModel(
            research_space_id=space.id,
            relation_id=relation_id,
            claim_id=claim_id,
            projection_origin="EXTRACTION",
            source_document_id=source_document_uuid,
            agent_run_id="run-paper-view",
            metadata_payload={},
        )
        participant_subject = ClaimParticipantModel(
            claim_id=claim_id,
            research_space_id=space.id,
            label="MED13",
            entity_id=source_id,
            role="SUBJECT",
            position=1,
            qualifiers={},
        )
        participant_object = ClaimParticipantModel(
            claim_id=claim_id,
            research_space_id=space.id,
            label="Cardiomyopathy",
            entity_id=target_id,
            role="OBJECT",
            position=2,
            qualifiers={},
        )
        evidence = ClaimEvidenceModel(
            claim_id=claim_id,
            source_document_id=source_document_uuid,
            agent_run_id="run-paper-view",
            sentence="MED13 variants were associated with cardiomyopathy in a curated cohort.",
            sentence_source="verbatim_span",
            sentence_confidence="high",
            sentence_rationale=None,
            figure_reference="Figure 2",
            table_reference=None,
            confidence=0.83,
            metadata_payload={},
        )
        relation_evidence = RelationEvidenceModel(
            relation_id=relation_id,
            confidence=0.83,
            evidence_summary="MED13 variants were associated with cardiomyopathy.",
            evidence_sentence=(
                "MED13 variants were associated with cardiomyopathy in a curated cohort."
            ),
            evidence_sentence_source="verbatim_span",
            evidence_sentence_confidence="high",
            evidence_sentence_rationale=None,
            source_document_id=source_document_uuid,
            evidence_tier="LITERATURE",
        )
        session.add(data_source)
        session.flush()
        session.add(document)
        session.add(relation)
        session.flush()
        session.add(claim)
        session.flush()
        session.add(projection_source)
        session.add(participant_subject)
        session.add(participant_object)
        session.add(evidence)
        session.add(relation_evidence)
        session.commit()

    response = test_client.get(
        f"/research-spaces/{space.id}/graph/views/paper/{source_document_uuid}",
        headers=headers,
        params={"claim_limit": 25},
    )
    assert response.status_code == 200, response.text
    payload = response.json()

    assert payload["view_type"] == "paper"
    assert payload["paper"]["id"] == str(source_document_uuid)
    assert payload["paper"]["source_type"] == SourceTypeEnum.PUBMED.value
    assert payload["counts"]["canonical_relations"] == 1
    assert payload["counts"]["claims"] == 1
    assert payload["counts"]["participants"] == 2
    assert payload["counts"]["evidence"] == 1
    assert payload["canonical_relations"][0]["id"] == str(relation_id)
