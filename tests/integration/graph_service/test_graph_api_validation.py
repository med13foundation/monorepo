from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from services.graph_api.app import create_app
from tests.graph_service_support import (
    build_graph_admin_headers,
    reset_graph_service_database,
)


@pytest.fixture(scope="function")
def graph_client() -> TestClient:
    reset_graph_service_database()
    with TestClient(create_app()) as client:
        yield client
    reset_graph_service_database()


def _create_space(graph_client: TestClient) -> tuple[str, dict[str, str]]:
    admin_headers = build_graph_admin_headers()
    space_id = str(uuid4())
    response = graph_client.put(
        f"/v1/admin/spaces/{space_id}",
        headers=admin_headers,
        json={
            "slug": f"graph-validation-{space_id[:8]}",
            "name": "Graph Validation Space",
            "description": "Validation coverage space.",
            "owner_id": str(uuid4()),
            "status": "active",
            "settings": {},
        },
    )
    assert response.status_code == 200, response.text
    return space_id, admin_headers


def test_graph_service_entity_list_requires_type_or_query(
    graph_client: TestClient,
) -> None:
    response = graph_client.get(
        f"/v1/spaces/{uuid4()}/entities",
        headers=build_graph_admin_headers(),
    )

    assert response.status_code == 400, response.text
    assert (
        response.json()["detail"]
        == "Provide either 'type' or 'q' when listing entities."
    )


def test_graph_service_protected_route_requires_authentication(
    graph_client: TestClient,
) -> None:
    response = graph_client.get(
        f"/v1/spaces/{uuid4()}/entities",
        params={"type": "GENE"},
    )

    assert response.status_code == 401, response.text
    assert response.json()["detail"] == "Authentication required"


def test_graph_service_entity_list_rejects_invalid_entity_ids(
    graph_client: TestClient,
) -> None:
    response = graph_client.get(
        f"/v1/spaces/{uuid4()}/entities",
        headers=build_graph_admin_headers(),
        params={"type": "GENE", "ids": "not-a-uuid"},
    )

    assert response.status_code == 400, response.text
    assert response.json()["detail"] == "Invalid entity id(s): not-a-uuid"


def test_graph_service_graph_document_rejects_seed_ids_in_starter_mode(
    graph_client: TestClient,
) -> None:
    response = graph_client.post(
        f"/v1/spaces/{uuid4()}/graph/document",
        headers=build_graph_admin_headers(),
        json={
            "mode": "starter",
            "seed_entity_ids": [str(uuid4())],
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

    assert response.status_code == 400, response.text
    assert (
        response.json()["detail"]
        == "seed_entity_ids must be empty when mode='starter'."
    )


def test_graph_service_graph_document_requires_seed_ids_in_seeded_mode(
    graph_client: TestClient,
) -> None:
    response = graph_client.post(
        f"/v1/spaces/{uuid4()}/graph/document",
        headers=build_graph_admin_headers(),
        json={
            "mode": "seeded",
            "seed_entity_ids": [],
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

    assert response.status_code == 400, response.text
    assert (
        response.json()["detail"] == "seed_entity_ids is required when mode='seeded'."
    )


def test_graph_service_graph_view_rejects_unknown_view_type(
    graph_client: TestClient,
) -> None:
    space_id, admin_headers = _create_space(graph_client)

    response = graph_client.get(
        f"/v1/spaces/{space_id}/graph/views/unknown/{uuid4()}",
        headers=admin_headers,
    )

    assert response.status_code == 400, response.text
    assert response.json()["detail"] == "Unsupported graph view type 'unknown'"


def test_graph_service_admin_membership_upsert_rejects_invalid_role(
    graph_client: TestClient,
) -> None:
    space_id, admin_headers = _create_space(graph_client)

    response = graph_client.put(
        f"/v1/admin/spaces/{space_id}/memberships/{uuid4()}",
        headers=admin_headers,
        json={"role": "invalid-role", "is_active": True},
    )

    assert response.status_code == 422, response.text
    detail = response.json()["detail"]
    assert isinstance(detail, list)
    assert detail[0]["loc"][-1] == "role"


def test_graph_service_relation_create_rejects_out_of_range_confidence(
    graph_client: TestClient,
) -> None:
    response = graph_client.post(
        f"/v1/spaces/{uuid4()}/relations",
        headers=build_graph_admin_headers(),
        json={
            "source_id": str(uuid4()),
            "relation_type": "ASSOCIATED_WITH",
            "target_id": str(uuid4()),
            "confidence": 1.5,
        },
    )

    assert response.status_code == 422, response.text
    detail = response.json()["detail"]
    assert isinstance(detail, list)
    assert detail[0]["loc"][-1] == "confidence"
