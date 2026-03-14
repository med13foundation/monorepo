from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient

from services.graph_api.app import create_app
from src.domain.entities.user import UserRole
from tests.graph_service_support import (
    build_graph_admin_headers,
    build_graph_auth_headers,
    reset_graph_service_database,
    seed_graph_service_dictionary_primitives,
)


def test_graph_service_write_and_read_workflow_end_to_end() -> None:
    reset_graph_service_database()
    try:
        with TestClient(create_app()) as client:
            admin_headers = build_graph_admin_headers()
            owner_id = uuid4()
            member_id = uuid4()
            space_id = uuid4()

            create_space_response = client.put(
                f"/v1/admin/spaces/{space_id}",
                headers=admin_headers,
                json={
                    "slug": f"graph-e2e-{space_id.hex[:8]}",
                    "name": "Graph E2E Space",
                    "description": "Standalone graph-service e2e workflow space.",
                    "owner_id": str(owner_id),
                    "status": "active",
                    "settings": {"review_threshold": 0.8},
                },
            )
            assert create_space_response.status_code == 200, create_space_response.text

            membership_response = client.put(
                f"/v1/admin/spaces/{space_id}/memberships/{member_id}",
                headers=admin_headers,
                json={"role": "researcher", "is_active": True},
            )
            assert membership_response.status_code == 200, membership_response.text
            seed_graph_service_dictionary_primitives()

            member_headers = build_graph_auth_headers(
                user_id=member_id,
                email=f"graph-member-{member_id.hex[:10]}@example.com",
                role=UserRole.RESEARCHER,
            )

            source_entity_response = client.post(
                f"/v1/spaces/{space_id}/entities",
                headers=member_headers,
                json={
                    "entity_type": "GENE",
                    "display_label": "MED13",
                    "metadata": {"source": "graph-e2e"},
                    "identifiers": {"hgnc_id": f"HGNC:{uuid4().hex[:8]}"},
                },
            )
            assert (
                source_entity_response.status_code == 201
            ), source_entity_response.text
            source_entity_id = source_entity_response.json()["entity"]["id"]

            target_entity_response = client.post(
                f"/v1/spaces/{space_id}/entities",
                headers=member_headers,
                json={
                    "entity_type": "PHENOTYPE",
                    "display_label": "Developmental delay",
                    "metadata": {"source": "graph-e2e"},
                    "identifiers": {"mesh_id": f"MESH:{uuid4().hex[:8]}"},
                },
            )
            assert (
                target_entity_response.status_code == 201
            ), target_entity_response.text
            target_entity_id = target_entity_response.json()["entity"]["id"]

            create_relation_response = client.post(
                f"/v1/spaces/{space_id}/relations",
                headers=admin_headers,
                json={
                    "source_id": source_entity_id,
                    "relation_type": "ASSOCIATED_WITH",
                    "target_id": target_entity_id,
                    "confidence": 0.87,
                    "evidence_summary": "Curated e2e relation.",
                    "evidence_sentence": "MED13 is associated with developmental delay.",
                    "evidence_sentence_source": "verbatim_span",
                    "evidence_sentence_confidence": "high",
                    "evidence_tier": "LITERATURE",
                },
            )
            assert (
                create_relation_response.status_code == 201
            ), create_relation_response.text
            relation_id = create_relation_response.json()["id"]

            export_response = client.get(
                f"/v1/spaces/{space_id}/graph/export",
                headers=member_headers,
            )
            assert export_response.status_code == 200, export_response.text
            export_payload = export_response.json()
            exported_node_ids = {node["id"] for node in export_payload["nodes"]}
            exported_edge_ids = {edge["id"] for edge in export_payload["edges"]}
            assert source_entity_id in exported_node_ids
            assert target_entity_id in exported_node_ids
            assert relation_id in exported_edge_ids

            graph_document_response = client.post(
                f"/v1/spaces/{space_id}/graph/document",
                headers=member_headers,
                json={
                    "mode": "seeded",
                    "seed_entity_ids": [source_entity_id],
                    "depth": 2,
                    "top_k": 25,
                    "max_nodes": 180,
                    "max_edges": 260,
                    "include_claims": True,
                    "include_evidence": True,
                    "max_claims": 250,
                    "evidence_limit_per_claim": 3,
                },
            )
            assert (
                graph_document_response.status_code == 200
            ), graph_document_response.text
            document_payload = graph_document_response.json()
            assert document_payload["meta"]["counts"]["entity_nodes"] >= 2
            assert document_payload["meta"]["counts"]["canonical_edges"] >= 1
    finally:
        reset_graph_service_database()
