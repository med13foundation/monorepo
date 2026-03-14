"""End-to-end graph-service workflow coverage for deterministic resolution."""

from __future__ import annotations

from uuid import uuid4

from tests import graph_service_support
from tests.graph_service_support import admin_headers, build_seeded_space_fixture

graph_client = graph_service_support.graph_client


def test_owner_entity_workflow_and_admin_relation_canonicalization(
    graph_client,
) -> None:
    fixture = build_seeded_space_fixture(slug_prefix="graph-e2e")
    owner_headers = fixture["headers"]
    space_id = fixture["space_id"]
    admin = admin_headers()
    suffix = uuid4().hex[:8]
    relation_type_id = f"GS_E2E_REL_{suffix}".upper()
    relation_synonym = f"modulates_{suffix.lower()}"

    source_response = graph_client.post(
        f"/v1/spaces/{space_id}/entities",
        headers=owner_headers,
        json={
            "entity_type": "GENE",
            "display_label": "MED13",
            "aliases": ["THRAP1"],
            "metadata": {},
            "identifiers": {},
        },
    )
    assert source_response.status_code == 201, source_response.text
    source_entity = source_response.json()["entity"]

    alias_lookup_response = graph_client.post(
        f"/v1/spaces/{space_id}/entities",
        headers=owner_headers,
        json={
            "entity_type": "GENE",
            "display_label": "THRAP1",
            "metadata": {},
            "identifiers": {},
        },
    )
    assert alias_lookup_response.status_code == 201, alias_lookup_response.text
    assert alias_lookup_response.json()["created"] is False
    assert alias_lookup_response.json()["entity"]["id"] == source_entity["id"]

    target_response = graph_client.post(
        f"/v1/spaces/{space_id}/entities",
        headers=owner_headers,
        json={
            "entity_type": "PHENOTYPE",
            "display_label": "Developmental delay",
            "metadata": {},
            "identifiers": {},
        },
    )
    assert target_response.status_code == 201, target_response.text
    target_entity = target_response.json()["entity"]

    relation_type_response = graph_client.post(
        "/v1/dictionary/relation-types",
        headers=admin,
        json={
            "id": relation_type_id,
            "display_name": f"Graph E2E Relation {suffix}",
            "description": "E2E relation type for standalone graph-service tests.",
            "domain_context": "general",
            "is_directional": True,
            "inverse_label": f"Inverse {suffix}",
            "source_ref": "graph-service-e2e",
        },
    )
    assert relation_type_response.status_code == 201, relation_type_response.text

    synonym_response = graph_client.post(
        "/v1/dictionary/relation-synonyms",
        headers=admin,
        json={
            "relation_type_id": relation_type_id,
            "synonym": relation_synonym,
            "source": "manual",
            "source_ref": "graph-service-e2e",
        },
    )
    assert synonym_response.status_code == 201, synonym_response.text

    constraint_response = graph_client.post(
        "/v1/dictionary/relation-constraints",
        headers=admin,
        json={
            "source_type": "GENE",
            "relation_type": relation_type_id,
            "target_type": "PHENOTYPE",
            "is_allowed": True,
            "requires_evidence": True,
            "source_ref": "graph-service-e2e",
        },
    )
    assert constraint_response.status_code == 201, constraint_response.text

    relation_response = graph_client.post(
        f"/v1/spaces/{space_id}/relations",
        headers=admin,
        json={
            "source_id": source_entity["id"],
            "target_id": target_entity["id"],
            "relation_type": relation_synonym,
            "confidence": 0.82,
            "evidence_summary": "Synthetic end-to-end evidence summary.",
            "source_document_ref": "doi:10.0000/graph-e2e",
        },
    )
    assert relation_response.status_code == 201, relation_response.text
    relation_payload = relation_response.json()
    assert relation_payload["relation_type"] == relation_type_id

    relation_list_response = graph_client.get(
        f"/v1/spaces/{space_id}/relations",
        headers=owner_headers,
        params={"relation_type": relation_type_id},
    )
    assert relation_list_response.status_code == 200, relation_list_response.text
    relation_list_payload = relation_list_response.json()
    assert relation_list_payload["total"] == 1
    assert relation_list_payload["relations"][0]["source_id"] == source_entity["id"]
    assert relation_list_payload["relations"][0]["target_id"] == target_entity["id"]
    assert relation_list_payload["relations"][0]["relation_type"] == relation_type_id
