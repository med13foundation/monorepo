"""Tests for Artana graph-connection adapter behavior."""

from __future__ import annotations

import os
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.domain.agents.contexts.graph_connection_context import GraphConnectionContext
from src.domain.agents.contracts.graph_connection import GraphConnectionContract
from src.domain.agents.models import ModelCapability, ModelSpec
from src.infrastructure.llm.adapters.graph_connection_agent_adapter import (
    ArtanaGraphConnectionAdapter,
)

_ADAPTER_MODULE = "src.infrastructure.llm.adapters.graph_connection_agent_adapter"


def _build_registry() -> MagicMock:
    registry = MagicMock()
    model_spec = ModelSpec(
        model_id="openai:gpt-5-mini",
        display_name="GPT-5 Mini",
        provider="openai",
        capabilities=frozenset({ModelCapability.EVIDENCE_EXTRACTION}),
        prompt_tokens_per_1k=0.00025,
        completion_tokens_per_1k=0.002,
        timeout_seconds=120.0,
        is_default=True,
    )
    registry.get_model.return_value = model_spec
    registry.get_default_model.return_value = model_spec
    registry.allow_runtime_model_overrides.return_value = True
    registry.validate_model_for_capability.return_value = True
    return registry


@contextmanager
def _build_adapter(
    *,
    with_services: bool = True,
):
    governance = MagicMock()
    governance.usage_limits.total_cost_usd = 1.0
    governance.usage_limits.max_turns = 8
    governance.usage_limits.max_tokens = 4096

    output = GraphConnectionContract(
        decision="generated",
        confidence_score=0.8,
        rationale="Cross-graph evidence supports candidates.",
        evidence=[],
        source_type="pubmed",
        research_space_id="space-1",
        seed_entity_id="entity-1",
        proposed_relations=[],
        rejected_candidates=[],
        shadow_mode=True,
        agent_run_id=None,
    )
    client = MagicMock()
    client.step = AsyncMock(return_value=SimpleNamespace(output=output))
    kernel = MagicMock()
    kernel.close = AsyncMock()
    model_port = MagicMock()
    model_port.aclose = AsyncMock()

    dictionary_service = MagicMock() if with_services else None
    graph_query_service = MagicMock() if with_services else None
    relation_repository = MagicMock() if with_services else None

    with (
        patch(f"{_ADAPTER_MODULE}._ARTANA_IMPORT_ERROR", None),
        patch(f"{_ADAPTER_MODULE}.get_model_registry", return_value=_build_registry()),
        patch(
            f"{_ADAPTER_MODULE}.GovernanceConfig.from_environment",
            return_value=governance,
        ),
        patch.object(
            ArtanaGraphConnectionAdapter,
            "_create_store",
            return_value=object(),
        ),
        patch.object(
            ArtanaGraphConnectionAdapter,
            "_create_tenant",
            return_value=object(),
        ),
        patch(f"{_ADAPTER_MODULE}._OpenAIChatModelPort", return_value=model_port),
        patch(f"{_ADAPTER_MODULE}.ArtanaKernel", return_value=kernel, create=True),
        patch(
            f"{_ADAPTER_MODULE}.SingleStepModelClient",
            return_value=client,
            create=True,
        ),
    ):
        yield ArtanaGraphConnectionAdapter(
            dictionary_service=dictionary_service,
            graph_query_service=graph_query_service,
            relation_repository=relation_repository,
        ), client


@pytest.mark.asyncio
async def test_discover_escalates_for_unsupported_source() -> None:
    with _build_adapter() as (adapter, client):
        context = GraphConnectionContext(
            seed_entity_id="entity-1",
            source_type="unsupported_source",
            research_space_id="space-1",
        )
        contract = await adapter.discover(context)

    assert contract.decision == "escalate"
    assert contract.confidence_score == 0.0
    assert "not supported" in contract.rationale
    client.step.assert_not_awaited()


@pytest.mark.asyncio
async def test_discover_uses_heuristic_fallback_without_openai_key() -> None:
    with (
        patch.dict(os.environ, {}, clear=True),
        _build_adapter(with_services=True) as (adapter, client),
    ):
        context = GraphConnectionContext(
            seed_entity_id="entity-2",
            source_type="clinvar",
            research_space_id="space-1",
        )
        contract = await adapter.discover(context)

    assert contract.decision == "fallback"
    assert contract.seed_entity_id == "entity-2"
    assert contract.proposed_relations == []
    client.step.assert_not_awaited()


@pytest.mark.asyncio
async def test_discover_uses_heuristic_fallback_without_services() -> None:
    with (
        patch.dict(os.environ, {"OPENAI_API_KEY": "test-openai-key"}, clear=True),
        _build_adapter(with_services=False) as (adapter, client),
    ):
        context = GraphConnectionContext(
            seed_entity_id="entity-3",
            source_type="clinvar",
            research_space_id="space-2",
        )
        contract = await adapter.discover(context)

    assert contract.decision == "fallback"
    assert "graph_tools_unavailable" in contract.rationale
    client.step.assert_not_awaited()


@pytest.mark.asyncio
async def test_discover_calls_artana_and_normalizes_contract() -> None:
    with (
        patch.dict(os.environ, {"OPENAI_API_KEY": "test-openai-key"}, clear=True),
        _build_adapter(with_services=True) as (adapter, client),
    ):
        context = GraphConnectionContext(
            seed_entity_id="entity-4",
            source_type="PUBMED",
            research_space_id="space-3",
            shadow_mode=False,
        )
        contract = await adapter.discover(context)

    assert contract.decision == "generated"
    assert contract.source_type == "pubmed"
    assert contract.seed_entity_id == "entity-4"
    assert contract.research_space_id == "space-3"
    assert contract.shadow_mode is False
    assert contract.agent_run_id is not None
    assert contract.agent_run_id.startswith("graph_connection:pubmed:")
    client.step.assert_awaited_once()
