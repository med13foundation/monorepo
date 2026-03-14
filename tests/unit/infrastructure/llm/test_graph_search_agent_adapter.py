"""Tests for Artana graph-search adapter behavior."""

from __future__ import annotations

import os
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from pydantic import BaseModel

from src.domain.agents.contexts.graph_search_context import GraphSearchContext
from src.domain.agents.contracts.graph_search import GraphSearchContract
from src.domain.agents.models import ModelCapability, ModelSpec
from src.graph.core.search_extension import GraphSearchConfig
from src.infrastructure.llm.adapters.graph_search_agent_adapter import (
    ArtanaGraphSearchAdapter,
    _OpenAIChatModelPort,
)

_ADAPTER_MODULE = "src.infrastructure.llm.adapters.graph_search_agent_adapter"


class _PortTestContract(BaseModel):
    answer: str


def _build_registry() -> MagicMock:
    registry = MagicMock()
    model_spec = ModelSpec(
        model_id="openai:gpt-5-mini",
        display_name="GPT-5 Mini",
        provider="openai",
        capabilities=frozenset({ModelCapability.QUERY_GENERATION}),
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
def _build_adapter(*, with_graph_service: bool = True):
    governance = MagicMock()
    governance.usage_limits.total_cost_usd = 1.0
    governance.usage_limits.max_turns = 8
    governance.usage_limits.max_tokens = 4096

    output = GraphSearchContract(
        decision="generated",
        confidence_score=0.87,
        rationale="Relevant entities identified.",
        evidence=[],
        research_space_id="space-1",
        original_query="q",
        interpreted_intent="q",
        query_plan_summary="search graph",
        total_results=0,
        results=[],
        executed_path="agent",
        warnings=[],
        agent_run_id=None,
    )
    client = MagicMock()
    client.step = AsyncMock(return_value=SimpleNamespace(output=output))
    kernel = MagicMock()
    kernel.close = AsyncMock()
    model_port = MagicMock()
    model_port.aclose = AsyncMock()

    graph_query_service = MagicMock() if with_graph_service else None

    with (
        patch(f"{_ADAPTER_MODULE}._ARTANA_IMPORT_ERROR", None),
        patch(f"{_ADAPTER_MODULE}.get_model_registry", return_value=_build_registry()),
        patch(
            f"{_ADAPTER_MODULE}.GovernanceConfig.from_environment",
            return_value=governance,
        ),
        patch.object(ArtanaGraphSearchAdapter, "_create_store", return_value=object()),
        patch.object(ArtanaGraphSearchAdapter, "_create_tenant", return_value=object()),
        patch(f"{_ADAPTER_MODULE}._OpenAIChatModelPort", return_value=model_port),
        patch(f"{_ADAPTER_MODULE}.ArtanaKernel", return_value=kernel, create=True),
        patch(
            f"{_ADAPTER_MODULE}.SingleStepModelClient",
            return_value=client,
            create=True,
        ),
    ):
        yield ArtanaGraphSearchAdapter(
            search_extension=GraphSearchConfig(system_prompt="Test search prompt"),
            graph_query_service=graph_query_service,
        ), client


@pytest.mark.asyncio
async def test_search_uses_fallback_without_openai_key() -> None:
    with (
        patch.dict(os.environ, {}, clear=True),
        _build_adapter(with_graph_service=True) as (adapter, client),
    ):
        context = GraphSearchContext(
            question="What evidence links MED13 to cardiac phenotypes?",
            research_space_id="space-1",
        )
        contract = await adapter.search(context)

    assert contract.decision == "fallback"
    assert contract.total_results == 0
    assert "API key is not configured" in contract.rationale
    client.step.assert_not_awaited()


@pytest.mark.asyncio
async def test_search_uses_fallback_without_graph_tools() -> None:
    with (
        patch.dict(os.environ, {"OPENAI_API_KEY": "test-openai-key"}, clear=True),
        _build_adapter(with_graph_service=False) as (adapter, client),
    ):
        context = GraphSearchContext(
            question="Find entities related to MED13",
            research_space_id="space-2",
        )
        contract = await adapter.search(context)

    assert contract.decision == "fallback"
    assert contract.results == []
    assert "tools are unavailable" in contract.rationale
    client.step.assert_not_awaited()


@pytest.mark.asyncio
async def test_search_calls_artana_and_normalizes_contract() -> None:
    with (
        patch.dict(os.environ, {"OPENAI_API_KEY": "test-openai-key"}, clear=True),
        _build_adapter(with_graph_service=True) as (adapter, client),
    ):
        context = GraphSearchContext(
            question="Find entities related to MED13",
            research_space_id="space-3",
        )
        contract = await adapter.search(context)

    assert contract.decision == "generated"
    assert contract.research_space_id == "space-3"
    assert contract.original_query == "Find entities related to MED13"
    assert contract.executed_path == "agent"
    assert contract.agent_run_id is not None
    assert contract.agent_run_id.startswith("graph_search:")
    client.step.assert_awaited_once()


def test_build_prompt_uses_search_extension_system_prompt() -> None:
    with _build_adapter(with_graph_service=True) as (adapter, _client):
        context = GraphSearchContext(
            question="Find entities related to MED13",
            research_space_id="space-3",
        )

        prompt = adapter._build_prompt(context)  # noqa: SLF001

    assert prompt.startswith("Test search prompt")


@pytest.mark.asyncio
async def test_openai_chat_model_port_computes_usage_cost() -> None:
    response = MagicMock(spec=httpx.Response)
    response.status_code = 200
    response.headers = {}
    response.raise_for_status.return_value = None
    response.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": '{"answer":"ok"}',
                },
            },
        ],
        "usage": {
            "prompt_tokens": 1500,
            "completion_tokens": 250,
        },
    }
    client = MagicMock()
    client.post = AsyncMock(return_value=response)

    port = _OpenAIChatModelPort(timeout_seconds=1.0)
    request = SimpleNamespace(
        model="openai:gpt-5-mini",
        prompt="hello",
        output_schema=_PortTestContract,
    )

    with (
        patch.object(
            port,
            "_resolve_openai_api_key",
            return_value="sk-test-value",
        ),
        patch.object(
            port,
            "_http_client",
            AsyncMock(return_value=client),
        ),
        patch(
            "src.infrastructure.llm.costs.get_model_registry",
            return_value=MagicMock(
                get_cost_config=MagicMock(
                    return_value={
                        "prompt_tokens_per_1k": 0.00025,
                        "completion_tokens_per_1k": 0.002,
                    },
                ),
            ),
        ),
    ):
        result = await port.complete(request)

    assert result.output.answer == "ok"
    assert result.usage.prompt_tokens == 1500
    assert result.usage.completion_tokens == 250
    assert result.usage.cost_usd == 0.000875
