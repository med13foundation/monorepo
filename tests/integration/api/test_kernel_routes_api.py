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
from src.database.seeds.seeder import (
    seed_entity_resolution_policies,
    seed_relation_constraints,
)
from src.domain.entities.user import UserRole
from src.domain.services.pubmed_ingestion import PubMedIngestionSummary
from src.infrastructure.security.jwt_provider import JWTProvider
from src.main import create_app
from src.models.database.base import Base
from src.models.database.kernel.dictionary import TransformRegistryModel
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
    db_engine = session_module.engine if _using_postgres() else test_engine
    reset_database(db_engine, Base.metadata)

    app = create_app()
    client = TestClient(app)
    yield client

    reset_database(db_engine, Base.metadata)


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
    created_variable = resp.json()
    assert created_variable["created_by"] == f"manual:{admin_user.id}"
    assert created_variable["review_status"] == "ACTIVE"

    # 2) Create two entities in the space (researcher/owner)
    headers = _auth_headers(researcher_user)

    with _session_for_api(db_session) as session:
        seed_entity_resolution_policies(session)

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

    # 4) Seed relation constraints so the triple is allowed
    with _session_for_api(db_session) as session:
        seed_relation_constraints(session)

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


def test_admin_dictionary_review_lifecycle(test_client, admin_user):
    create_response = test_client.post(
        "/admin/dictionary/variables",
        headers=_auth_headers(admin_user),
        json={
            "id": "VAR_REVIEW_LIFECYCLE",
            "canonical_name": "review_lifecycle",
            "display_name": "Review Lifecycle",
            "data_type": "STRING",
            "domain_context": "general",
            "sensitivity": "INTERNAL",
            "constraints": {},
            "description": "Variable used for review lifecycle tests",
            "source_ref": "paper:pmid:12345",
        },
    )
    assert create_response.status_code == 201, create_response.text
    payload = create_response.json()
    assert payload["source_ref"] == "paper:pmid:12345"
    assert payload["review_status"] == "ACTIVE"

    set_pending_response = test_client.patch(
        "/admin/dictionary/variables/VAR_REVIEW_LIFECYCLE/review-status",
        headers=_auth_headers(admin_user),
        json={"review_status": "PENDING_REVIEW"},
    )
    assert set_pending_response.status_code == 200, set_pending_response.text
    pending_payload = set_pending_response.json()
    assert pending_payload["review_status"] == "PENDING_REVIEW"
    assert pending_payload["reviewed_by"] == f"manual:{admin_user.id}"

    revoke_response = test_client.post(
        "/admin/dictionary/variables/VAR_REVIEW_LIFECYCLE/revoke",
        headers=_auth_headers(admin_user),
        json={"reason": "Deprecated variable"},
    )
    assert revoke_response.status_code == 200, revoke_response.text
    revoked_payload = revoke_response.json()
    assert revoked_payload["review_status"] == "REVOKED"
    assert revoked_payload["revocation_reason"] == "Deprecated variable"
    assert revoked_payload["is_active"] is False
    assert revoked_payload["valid_to"] is not None

    reactivate_response = test_client.patch(
        "/admin/dictionary/variables/VAR_REVIEW_LIFECYCLE/review-status",
        headers=_auth_headers(admin_user),
        json={"review_status": "ACTIVE"},
    )
    assert reactivate_response.status_code == 200, reactivate_response.text
    reactivated_payload = reactivate_response.json()
    assert reactivated_payload["review_status"] == "ACTIVE"
    assert reactivated_payload["is_active"] is True
    assert reactivated_payload["valid_to"] is None

    changelog_response = test_client.get(
        "/admin/dictionary/changelog",
        headers=_auth_headers(admin_user),
        params={
            "table_name": "variable_definitions",
            "record_id": "VAR_REVIEW_LIFECYCLE",
        },
    )
    assert changelog_response.status_code == 200, changelog_response.text
    actions = {
        str(entry["action"]) for entry in changelog_response.json()["changelog_entries"]
    }
    assert "CREATE" in actions
    assert "UPDATE" in actions
    assert "REVOKE" in actions


def test_admin_dictionary_type_endpoints(test_client, admin_user):
    create_entity_type_response = test_client.post(
        "/admin/dictionary/entity-types",
        headers=_auth_headers(admin_user),
        json={
            "id": "ENTITY_TEST_DOMAIN_ITEM",
            "display_name": "Entity Test Domain Item",
            "description": "Entity type created from integration test",
            "domain_context": "general",
            "expected_properties": {"required_keys": ["code"]},
        },
    )
    assert (
        create_entity_type_response.status_code == 201
    ), create_entity_type_response.text
    created_entity_payload = create_entity_type_response.json()
    assert created_entity_payload["id"] == "ENTITY_TEST_DOMAIN_ITEM"
    assert created_entity_payload["created_by"] == f"manual:{admin_user.id}"

    create_relation_type_response = test_client.post(
        "/admin/dictionary/relation-types",
        headers=_auth_headers(admin_user),
        json={
            "id": "REL_TEST_LINKS_TO",
            "display_name": "Test Links To",
            "description": "Relation type created from integration test",
            "domain_context": "general",
            "is_directional": True,
            "inverse_label": "Linked From",
        },
    )
    assert (
        create_relation_type_response.status_code == 201
    ), create_relation_type_response.text
    created_relation_payload = create_relation_type_response.json()
    assert created_relation_payload["id"] == "REL_TEST_LINKS_TO"
    assert created_relation_payload["created_by"] == f"manual:{admin_user.id}"

    get_entity_type_response = test_client.get(
        "/admin/dictionary/entity-types/ENTITY_TEST_DOMAIN_ITEM",
        headers=_auth_headers(admin_user),
    )
    assert get_entity_type_response.status_code == 200, get_entity_type_response.text
    assert get_entity_type_response.json()["id"] == "ENTITY_TEST_DOMAIN_ITEM"

    get_relation_type_response = test_client.get(
        "/admin/dictionary/relation-types/REL_TEST_LINKS_TO",
        headers=_auth_headers(admin_user),
    )
    assert (
        get_relation_type_response.status_code == 200
    ), get_relation_type_response.text
    assert get_relation_type_response.json()["id"] == "REL_TEST_LINKS_TO"

    list_entity_types_response = test_client.get(
        "/admin/dictionary/entity-types",
        headers=_auth_headers(admin_user),
        params={"domain_context": "general"},
    )
    assert (
        list_entity_types_response.status_code == 200
    ), list_entity_types_response.text
    assert list_entity_types_response.json()["total"] >= 1

    list_relation_types_response = test_client.get(
        "/admin/dictionary/relation-types",
        headers=_auth_headers(admin_user),
        params={"domain_context": "general"},
    )
    assert (
        list_relation_types_response.status_code == 200
    ), list_relation_types_response.text
    assert list_relation_types_response.json()["total"] >= 1

    set_entity_review_status_response = test_client.patch(
        "/admin/dictionary/entity-types/ENTITY_TEST_DOMAIN_ITEM/review-status",
        headers=_auth_headers(admin_user),
        json={"review_status": "PENDING_REVIEW"},
    )
    assert (
        set_entity_review_status_response.status_code == 200
    ), set_entity_review_status_response.text
    assert set_entity_review_status_response.json()["review_status"] == "PENDING_REVIEW"

    revoke_entity_type_response = test_client.post(
        "/admin/dictionary/entity-types/ENTITY_TEST_DOMAIN_ITEM/revoke",
        headers=_auth_headers(admin_user),
        json={"reason": "No longer in use"},
    )
    assert (
        revoke_entity_type_response.status_code == 200
    ), revoke_entity_type_response.text
    assert revoke_entity_type_response.json()["review_status"] == "REVOKED"
    assert revoke_entity_type_response.json()["is_active"] is False
    assert revoke_entity_type_response.json()["valid_to"] is not None

    set_relation_review_status_response = test_client.patch(
        "/admin/dictionary/relation-types/REL_TEST_LINKS_TO/review-status",
        headers=_auth_headers(admin_user),
        json={"review_status": "PENDING_REVIEW"},
    )
    assert (
        set_relation_review_status_response.status_code == 200
    ), set_relation_review_status_response.text
    assert (
        set_relation_review_status_response.json()["review_status"] == "PENDING_REVIEW"
    )

    revoke_relation_type_response = test_client.post(
        "/admin/dictionary/relation-types/REL_TEST_LINKS_TO/revoke",
        headers=_auth_headers(admin_user),
        json={"reason": "No longer in use"},
    )
    assert (
        revoke_relation_type_response.status_code == 200
    ), revoke_relation_type_response.text
    assert revoke_relation_type_response.json()["review_status"] == "REVOKED"
    assert revoke_relation_type_response.json()["is_active"] is False
    assert revoke_relation_type_response.json()["valid_to"] is not None


def test_admin_dictionary_merge_endpoints(test_client, admin_user):
    source_variable_response = test_client.post(
        "/admin/dictionary/variables",
        headers=_auth_headers(admin_user),
        json={
            "id": "VAR_MERGE_SOURCE",
            "canonical_name": "merge_source",
            "display_name": "Merge Source",
            "data_type": "STRING",
            "domain_context": "general",
            "sensitivity": "INTERNAL",
            "constraints": {},
            "description": "Source variable for merge integration test",
        },
    )
    assert source_variable_response.status_code == 201, source_variable_response.text

    target_variable_response = test_client.post(
        "/admin/dictionary/variables",
        headers=_auth_headers(admin_user),
        json={
            "id": "VAR_MERGE_TARGET",
            "canonical_name": "merge_target",
            "display_name": "Merge Target",
            "data_type": "STRING",
            "domain_context": "general",
            "sensitivity": "INTERNAL",
            "constraints": {},
            "description": "Target variable for merge integration test",
        },
    )
    assert target_variable_response.status_code == 201, target_variable_response.text

    merge_variable_response = test_client.post(
        "/admin/dictionary/variables/VAR_MERGE_SOURCE/merge",
        headers=_auth_headers(admin_user),
        json={
            "target_id": "VAR_MERGE_TARGET",
            "reason": "Duplicate variable definition",
        },
    )
    assert merge_variable_response.status_code == 200, merge_variable_response.text
    merged_variable_payload = merge_variable_response.json()
    assert merged_variable_payload["review_status"] == "REVOKED"
    assert merged_variable_payload["is_active"] is False
    assert merged_variable_payload["superseded_by"] == "VAR_MERGE_TARGET"
    assert merged_variable_payload["valid_to"] is not None

    source_entity_type_response = test_client.post(
        "/admin/dictionary/entity-types",
        headers=_auth_headers(admin_user),
        json={
            "id": "ENTITY_MERGE_SOURCE",
            "display_name": "Entity Merge Source",
            "description": "Source entity type for merge integration test",
            "domain_context": "general",
            "expected_properties": {},
        },
    )
    assert (
        source_entity_type_response.status_code == 201
    ), source_entity_type_response.text

    target_entity_type_response = test_client.post(
        "/admin/dictionary/entity-types",
        headers=_auth_headers(admin_user),
        json={
            "id": "ENTITY_MERGE_TARGET",
            "display_name": "Entity Merge Target",
            "description": "Target entity type for merge integration test",
            "domain_context": "general",
            "expected_properties": {},
        },
    )
    assert (
        target_entity_type_response.status_code == 201
    ), target_entity_type_response.text

    merge_entity_type_response = test_client.post(
        "/admin/dictionary/entity-types/ENTITY_MERGE_SOURCE/merge",
        headers=_auth_headers(admin_user),
        json={
            "target_id": "ENTITY_MERGE_TARGET",
            "reason": "Duplicate entity type",
        },
    )
    assert (
        merge_entity_type_response.status_code == 200
    ), merge_entity_type_response.text
    merged_entity_type_payload = merge_entity_type_response.json()
    assert merged_entity_type_payload["review_status"] == "REVOKED"
    assert merged_entity_type_payload["is_active"] is False
    assert merged_entity_type_payload["superseded_by"] == "ENTITY_MERGE_TARGET"
    assert merged_entity_type_payload["valid_to"] is not None

    source_relation_type_response = test_client.post(
        "/admin/dictionary/relation-types",
        headers=_auth_headers(admin_user),
        json={
            "id": "REL_MERGE_SOURCE",
            "display_name": "Relation Merge Source",
            "description": "Source relation type for merge integration test",
            "domain_context": "general",
            "is_directional": True,
            "inverse_label": "Merged From",
        },
    )
    assert (
        source_relation_type_response.status_code == 201
    ), source_relation_type_response.text

    target_relation_type_response = test_client.post(
        "/admin/dictionary/relation-types",
        headers=_auth_headers(admin_user),
        json={
            "id": "REL_MERGE_TARGET",
            "display_name": "Relation Merge Target",
            "description": "Target relation type for merge integration test",
            "domain_context": "general",
            "is_directional": True,
            "inverse_label": "Merged To",
        },
    )
    assert (
        target_relation_type_response.status_code == 201
    ), target_relation_type_response.text

    merge_relation_type_response = test_client.post(
        "/admin/dictionary/relation-types/REL_MERGE_SOURCE/merge",
        headers=_auth_headers(admin_user),
        json={
            "target_id": "REL_MERGE_TARGET",
            "reason": "Duplicate relation type",
        },
    )
    assert (
        merge_relation_type_response.status_code == 200
    ), merge_relation_type_response.text
    merged_relation_type_payload = merge_relation_type_response.json()
    assert merged_relation_type_payload["review_status"] == "REVOKED"
    assert merged_relation_type_payload["is_active"] is False
    assert merged_relation_type_payload["superseded_by"] == "REL_MERGE_TARGET"
    assert merged_relation_type_payload["valid_to"] is not None

    changelog_response = test_client.get(
        "/admin/dictionary/changelog",
        headers=_auth_headers(admin_user),
        params={
            "table_name": "variable_definitions",
            "record_id": "VAR_MERGE_SOURCE",
        },
    )
    assert changelog_response.status_code == 200, changelog_response.text
    changelog_actions = {
        str(entry["action"]) for entry in changelog_response.json()["changelog_entries"]
    }
    assert "MERGE" in changelog_actions


def test_admin_dictionary_value_set_endpoints(test_client, admin_user):
    create_variable_response = test_client.post(
        "/admin/dictionary/variables",
        headers=_auth_headers(admin_user),
        json={
            "id": "VAR_TEST_CODED_STATUS",
            "canonical_name": "test_coded_status",
            "display_name": "Test Coded Status",
            "data_type": "CODED",
            "domain_context": "general",
            "sensitivity": "INTERNAL",
            "constraints": {},
            "description": "Coded variable for value set integration test",
        },
    )
    assert create_variable_response.status_code == 201, create_variable_response.text

    create_value_set_response = test_client.post(
        "/admin/dictionary/value-sets",
        headers=_auth_headers(admin_user),
        json={
            "id": "VS_TEST_CODED_STATUS",
            "variable_id": "VAR_TEST_CODED_STATUS",
            "name": "Test coded statuses",
            "description": "Allowed coded statuses for integration tests",
            "is_extensible": True,
            "source_ref": "test:value-set",
        },
    )
    assert create_value_set_response.status_code == 201, create_value_set_response.text
    created_value_set = create_value_set_response.json()
    assert created_value_set["id"] == "VS_TEST_CODED_STATUS"
    assert created_value_set["variable_id"] == "VAR_TEST_CODED_STATUS"
    assert created_value_set["review_status"] == "ACTIVE"
    assert created_value_set["created_by"] == f"manual:{admin_user.id}"

    list_value_sets_response = test_client.get(
        "/admin/dictionary/value-sets",
        headers=_auth_headers(admin_user),
        params={"variable_id": "VAR_TEST_CODED_STATUS"},
    )
    assert list_value_sets_response.status_code == 200, list_value_sets_response.text
    list_payload = list_value_sets_response.json()
    assert list_payload["total"] == 1
    assert list_payload["value_sets"][0]["id"] == "VS_TEST_CODED_STATUS"

    create_item_response = test_client.post(
        "/admin/dictionary/value-sets/VS_TEST_CODED_STATUS/items",
        headers=_auth_headers(admin_user),
        json={
            "code": "APPROVED",
            "display_label": "Approved",
            "synonyms": ["approved", "ok_to_use"],
            "sort_order": 10,
            "source_ref": "test:value-set-item",
        },
    )
    assert create_item_response.status_code == 201, create_item_response.text
    created_item = create_item_response.json()
    assert created_item["code"] == "APPROVED"
    assert created_item["synonyms"] == ["approved", "ok_to_use"]
    assert created_item["is_active"] is True

    list_items_response = test_client.get(
        "/admin/dictionary/value-sets/VS_TEST_CODED_STATUS/items",
        headers=_auth_headers(admin_user),
    )
    assert list_items_response.status_code == 200, list_items_response.text
    items_payload = list_items_response.json()
    assert items_payload["total"] == 1
    item_id = int(items_payload["items"][0]["id"])

    deactivate_item_response = test_client.patch(
        f"/admin/dictionary/value-set-items/{item_id}/active",
        headers=_auth_headers(admin_user),
        json={
            "is_active": False,
            "revocation_reason": "Deprecated code",
        },
    )
    assert deactivate_item_response.status_code == 200, deactivate_item_response.text
    deactivated_item = deactivate_item_response.json()
    assert deactivated_item["is_active"] is False
    assert deactivated_item["review_status"] == "REVOKED"
    assert deactivated_item["revocation_reason"] == "Deprecated code"

    list_active_items_response = test_client.get(
        "/admin/dictionary/value-sets/VS_TEST_CODED_STATUS/items",
        headers=_auth_headers(admin_user),
    )
    assert (
        list_active_items_response.status_code == 200
    ), list_active_items_response.text
    assert list_active_items_response.json()["total"] == 0

    list_all_items_response = test_client.get(
        "/admin/dictionary/value-sets/VS_TEST_CODED_STATUS/items",
        headers=_auth_headers(admin_user),
        params={"include_inactive": True},
    )
    assert list_all_items_response.status_code == 200, list_all_items_response.text
    all_items_payload = list_all_items_response.json()
    assert all_items_payload["total"] == 1
    assert all_items_payload["items"][0]["is_active"] is False


def test_admin_dictionary_search_and_reembed_endpoints(test_client, admin_user):
    create_variable_response = test_client.post(
        "/admin/dictionary/variables",
        headers=_auth_headers(admin_user),
        json={
            "id": "VAR_SEARCH_FLAG",
            "canonical_name": "search_flag",
            "display_name": "Search Flag",
            "data_type": "STRING",
            "domain_context": "general",
            "sensitivity": "INTERNAL",
            "constraints": {},
            "description": "A searchable integration-test dictionary variable",
        },
    )
    assert create_variable_response.status_code == 201, create_variable_response.text

    create_entity_type_response = test_client.post(
        "/admin/dictionary/entity-types",
        headers=_auth_headers(admin_user),
        json={
            "id": "ENTITY_SEARCH_ITEM",
            "display_name": "Entity Search Item",
            "description": "Entity type used for dictionary search tests",
            "domain_context": "general",
            "expected_properties": {},
        },
    )
    assert (
        create_entity_type_response.status_code == 201
    ), create_entity_type_response.text

    create_relation_type_response = test_client.post(
        "/admin/dictionary/relation-types",
        headers=_auth_headers(admin_user),
        json={
            "id": "REL_SEARCH_LINKS",
            "display_name": "Search Links",
            "description": "Relation type used for dictionary search tests",
            "domain_context": "general",
            "is_directional": True,
        },
    )
    assert (
        create_relation_type_response.status_code == 201
    ), create_relation_type_response.text

    search_response = test_client.get(
        "/admin/dictionary/search",
        headers=_auth_headers(admin_user),
        params={
            "terms": "Search Flag",
            "dimensions": ["variables", "entity_types"],
            "limit": 20,
        },
    )
    assert search_response.status_code == 200, search_response.text
    search_payload = search_response.json()
    assert search_payload["total"] >= 1
    first_result = search_payload["results"][0]
    assert first_result["dimension"] in {"variables", "entity_types"}
    assert first_result["match_method"] in {"exact", "synonym", "fuzzy", "vector"}

    by_domain_response = test_client.get(
        "/admin/dictionary/search/by-domain/general",
        headers=_auth_headers(admin_user),
        params={"limit": 50},
    )
    assert by_domain_response.status_code == 200, by_domain_response.text
    by_domain_payload = by_domain_response.json()
    assert by_domain_payload["total"] >= 3

    reembed_response = test_client.post(
        "/admin/dictionary/reembed",
        headers=_auth_headers(admin_user),
        json={
            "limit_per_dimension": 5,
            "source_ref": "test:dictionary-reembed",
        },
    )
    assert reembed_response.status_code == 200, reembed_response.text
    reembed_payload = reembed_response.json()
    assert reembed_payload["updated_records"] >= 3


def test_admin_dictionary_transform_endpoints(
    test_client,
    db_session,
    admin_user,
) -> None:
    with _session_for_api(db_session) as session:
        session.add(
            TransformRegistryModel(
                id="TR_TEST_PROMOTE",
                input_unit="mg",
                output_unit="g",
                category="UNIT_CONVERSION",
                implementation_ref="func:std_lib.convert.mg_to_g",
                status="ACTIVE",
                is_deterministic=True,
                is_production_allowed=False,
                test_input=2500,
                expected_output=2.5,
                description="Integration-test transform",
                created_by="seed",
            ),
        )
        session.commit()

    list_before = test_client.get(
        "/admin/dictionary/transforms",
        headers=_auth_headers(admin_user),
    )
    assert list_before.status_code == 200, list_before.text
    list_before_payload = list_before.json()
    assert list_before_payload["total"] >= 1
    listed_ids = {item["id"] for item in list_before_payload["transforms"]}
    assert "TR_TEST_PROMOTE" in listed_ids

    verify_response = test_client.post(
        "/admin/dictionary/transforms/TR_TEST_PROMOTE/verify",
        headers=_auth_headers(admin_user),
    )
    assert verify_response.status_code == 200, verify_response.text
    verify_payload = verify_response.json()
    assert verify_payload["transform_id"] == "TR_TEST_PROMOTE"
    assert verify_payload["passed"] is True

    promote_response = test_client.patch(
        "/admin/dictionary/transforms/TR_TEST_PROMOTE/promote",
        headers=_auth_headers(admin_user),
    )
    assert promote_response.status_code == 200, promote_response.text
    promoted = promote_response.json()
    assert promoted["id"] == "TR_TEST_PROMOTE"
    assert promoted["is_production_allowed"] is True

    list_production_only = test_client.get(
        "/admin/dictionary/transforms",
        headers=_auth_headers(admin_user),
        params={"production_only": True},
    )
    assert list_production_only.status_code == 200, list_production_only.text
    production_ids = {item["id"] for item in list_production_only.json()["transforms"]}
    assert "TR_TEST_PROMOTE" in production_ids


def test_kernel_entity_rejects_unknown_type(
    test_client,
    db_session,
    researcher_user,
    space,
):
    headers = _auth_headers(researcher_user)

    with _session_for_api(db_session) as session:
        seed_entity_resolution_policies(session)

    response = test_client.post(
        f"/research-spaces/{space.id}/entities",
        headers=headers,
        json={
            "entity_type": "UNKNOWN_TYPE",
            "display_label": "Suspicious",
            "metadata": {},
            "identifiers": {"custom": "x"},
        },
    )
    assert response.status_code == 400
    assert response.json()["detail"].startswith("Unknown entity_type")


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
            source = UserDataSourceModel(
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
            )
            session.add(source)
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
