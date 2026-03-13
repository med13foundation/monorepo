"""Unit tests for graph-service pipeline orchestration helpers."""

from __future__ import annotations

from uuid import uuid4

import pytest

from src.domain.agents.contracts.graph_connection import ProposedRelation
from src.domain.agents.contracts.graph_search import GraphSearchContract
from src.domain.entities.user import User, UserRole, UserStatus
from src.infrastructure.graph_service.pipeline import (
    GraphServiceGraphSearchAdapter,
    build_graph_connection_seed_runner_for_service,
    build_graph_connection_seed_runner_for_user,
    build_graph_search_service_for_service,
    build_graph_search_service_for_user,
)
from src.infrastructure.graph_service.runtime import (
    build_graph_service_bearer_token_for_service,
    build_graph_service_bearer_token_for_user,
)
from src.infrastructure.security.jwt_provider import JWTProvider


class _StubGraphServiceClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []
        self.closed = False

    def discover_entity_connections(self, **kwargs: object):
        self.calls.append(kwargs)

        class _Response:
            seed_entity_id = str(kwargs["entity_id"])
            research_space_id = str(kwargs["space_id"])
            status = "discovered"
            reason = "processed"
            review_required = False
            shadow_mode = bool(kwargs["shadow_mode"])
            wrote_to_graph = True
            run_id = "graph-service-run-001"
            proposed_relations_count = 2
            persisted_relations_count = 1
            rejected_candidates_count = 1
            errors = ["fallback"]

        return _Response()

    def close(self) -> None:
        self.closed = True


class _StubGraphSearchClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []
        self.closed = False

    def search_graph(self, **kwargs: object) -> GraphSearchContract:
        self.calls.append(kwargs)
        return GraphSearchContract(
            confidence_score=0.9,
            rationale="Search completed.",
            evidence=[],
            decision="generated",
            research_space_id=str(kwargs["space_id"]),
            original_query=str(kwargs["question"]),
            interpreted_intent=str(kwargs["question"]),
            query_plan_summary="Plan",
            total_results=1,
            results=[],
            executed_path="agent",
            warnings=[],
            agent_run_id="run-1",
        )

    def close(self) -> None:
        self.closed = True


def _build_user() -> User:
    return User(
        id=uuid4(),
        email="graph-runner@example.com",
        username="graph-runner",
        full_name="Graph Runner",
        hashed_password="hashed",
        role=UserRole.RESEARCHER,
        status=UserStatus.ACTIVE,
    )


@pytest.mark.asyncio
async def test_graph_connection_seed_runner_calls_graph_service_client() -> None:
    user = _build_user()
    stub_client = _StubGraphServiceClient()
    runner = build_graph_connection_seed_runner_for_user(
        user,
        client_factory=lambda _: stub_client,
    )
    source_id = str(uuid4())
    space_id = str(uuid4())
    seed_entity_id = str(uuid4())

    outcome = await runner(
        source_id=source_id,
        research_space_id=space_id,
        seed_entity_id=seed_entity_id,
        source_type="pubmed",
        model_id="model-1",
        relation_types=["ASSOCIATED_WITH"],
        max_depth=3,
        shadow_mode=True,
        pipeline_run_id="pipeline-run-001",
        fallback_relations=(
            ProposedRelation(
                source_id=seed_entity_id,
                relation_type="ASSOCIATED_WITH",
                target_id=str(uuid4()),
                confidence=0.55,
                evidence_summary="Fallback relation",
                supporting_provenance_ids=[],
                supporting_document_count=0,
                reasoning="Fallback reasoning",
            ),
        ),
    )

    assert outcome.run_id == "graph-service-run-001"
    assert outcome.persisted_relations_count == 1
    assert stub_client.closed is True
    assert stub_client.calls[0]["source_id"] == source_id
    assert stub_client.calls[0]["pipeline_run_id"] == "pipeline-run-001"
    fallback_relations = stub_client.calls[0]["fallback_relations"]
    assert isinstance(fallback_relations, list)
    assert len(fallback_relations) == 1


@pytest.mark.asyncio
async def test_graph_connection_seed_runner_for_service_calls_graph_service_client() -> (
    None
):
    stub_client = _StubGraphServiceClient()
    runner = build_graph_connection_seed_runner_for_service(
        client_factory=lambda: stub_client,
    )

    outcome = await runner(
        source_id=str(uuid4()),
        research_space_id=str(uuid4()),
        seed_entity_id=str(uuid4()),
        source_type="clinvar",
        model_id=None,
        relation_types=None,
        max_depth=2,
        shadow_mode=None,
        pipeline_run_id="run-http-service-001",
        fallback_relations=None,
    )

    assert outcome.run_id == "graph-service-run-001"
    assert stub_client.closed is True
    assert stub_client.calls[0]["pipeline_run_id"] == "run-http-service-001"


@pytest.mark.asyncio
async def test_graph_search_adapter_calls_graph_service_client() -> None:
    stub_client = _StubGraphSearchClient()
    adapter = GraphServiceGraphSearchAdapter(client_factory=lambda: stub_client)

    contract = await adapter.search(
        question="Find seeds",
        research_space_id=str(uuid4()),
        max_depth=1,
        top_k=5,
        include_evidence_chains=False,
        force_agent=True,
        model_id="model-1",
    )

    assert contract.agent_run_id == "run-1"
    assert stub_client.closed is True
    assert stub_client.calls[0]["force_agent"] is True
    assert stub_client.calls[0]["model_id"] == "model-1"


def test_build_graph_search_service_for_service_returns_adapter() -> None:
    adapter = build_graph_search_service_for_service(
        client_factory=lambda: _StubGraphSearchClient(),
    )

    assert isinstance(adapter, GraphServiceGraphSearchAdapter)


@pytest.mark.asyncio
async def test_build_graph_search_service_for_user_uses_user_client_factory() -> None:
    user = _build_user()
    stub_client = _StubGraphSearchClient()
    captured_users: list[User] = []
    adapter = build_graph_search_service_for_user(
        user,
        client_factory=lambda resolved_user: (
            captured_users.append(resolved_user) or stub_client
        ),
    )

    contract = await adapter.search(
        question="Infer graph seeds",
        research_space_id=str(uuid4()),
        max_depth=1,
        top_k=5,
        include_evidence_chains=False,
        force_agent=True,
    )

    assert contract.agent_run_id == "run-1"
    assert captured_users == [user]
    assert stub_client.closed is True


def test_build_graph_service_bearer_token_for_user_uses_shared_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = _build_user()
    monkeypatch.setenv(
        "GRAPH_JWT_SECRET",
        "med13-resource-library-backend-jwt-secret-for-development-2026-01",
    )

    token = build_graph_service_bearer_token_for_user(user)
    payload = JWTProvider(
        secret_key="med13-resource-library-backend-jwt-secret-for-development-2026-01",
    ).decode_token(token)

    assert payload["sub"] == str(user.id)
    assert payload["role"] == user.role.value
    assert payload["graph_admin"] is False


def test_build_graph_service_bearer_token_for_service_uses_graph_admin_claim(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "GRAPH_JWT_SECRET",
        "med13-resource-library-backend-jwt-secret-for-development-2026-01",
    )
    monkeypatch.setenv(
        "GRAPH_SERVICE_SERVICE_USER_ID",
        "00000000-0000-0000-0000-000000000099",
    )

    token = build_graph_service_bearer_token_for_service()
    payload = JWTProvider(
        secret_key="med13-resource-library-backend-jwt-secret-for-development-2026-01",
    ).decode_token(token)

    assert payload["sub"] == "00000000-0000-0000-0000-000000000099"
    assert payload["role"] == UserRole.VIEWER.value
    assert payload["graph_admin"] is True
