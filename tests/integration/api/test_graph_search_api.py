"""Integration tests for graph search API routes."""

from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient

from src.main import create_app


def test_graph_search_requires_authentication() -> None:
    app = create_app()
    client = TestClient(app)

    response = client.post(
        f"/research-spaces/{uuid4()}/graph/search",
        json={"question": "What genes are associated with cardiomyopathy?"},
    )

    assert response.status_code == 401
