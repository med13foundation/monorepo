"""Tests for Flujo graph-search adapter fallback and tool wiring behavior."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.domain.agents.contexts.graph_search_context import GraphSearchContext
from src.infrastructure.llm.adapters.graph_search_agent_adapter import (
    FlujoGraphSearchAdapter,
)


def _build_adapter() -> FlujoGraphSearchAdapter:
    with (
        patch(
            "src.infrastructure.llm.adapters.graph_search_agent_adapter.get_state_backend",
            return_value=MagicMock(),
        ),
        patch(
            "src.infrastructure.llm.adapters.graph_search_agent_adapter.get_model_registry",
            return_value=MagicMock(),
        ),
        patch(
            "src.infrastructure.llm.adapters.graph_search_agent_adapter.get_lifecycle_manager",
            return_value=MagicMock(),
        ),
    ):
        return FlujoGraphSearchAdapter()


@pytest.mark.asyncio
async def test_search_uses_fallback_without_openai_key() -> None:
    adapter = _build_adapter()
    context = GraphSearchContext(
        question="What evidence links MED13 to cardiac phenotypes?",
        research_space_id="space-1",
    )

    with patch.object(
        FlujoGraphSearchAdapter,
        "_has_openai_key",
        return_value=False,
    ):
        contract = await adapter.search(context)

    assert contract.decision == "fallback"
    assert contract.total_results == 0
    assert "API key is not configured" in contract.rationale


@pytest.mark.asyncio
async def test_search_uses_fallback_without_graph_tools() -> None:
    adapter = _build_adapter()
    context = GraphSearchContext(
        question="Find entities related to MED13",
        research_space_id="space-2",
    )

    with patch.object(
        FlujoGraphSearchAdapter,
        "_has_openai_key",
        return_value=True,
    ):
        contract = await adapter.search(context)

    assert contract.decision == "fallback"
    assert contract.results == []
    assert "tools are unavailable" in contract.rationale


def test_get_or_create_pipeline_binds_graph_search_tools() -> None:
    mock_pipeline = MagicMock()
    lifecycle_manager = MagicMock()
    graph_query_service = MagicMock()

    with (
        patch(
            "src.infrastructure.llm.adapters.graph_search_agent_adapter.get_state_backend",
            return_value=MagicMock(),
        ),
        patch(
            "src.infrastructure.llm.adapters.graph_search_agent_adapter.get_model_registry",
            return_value=MagicMock(),
        ),
        patch(
            "src.infrastructure.llm.adapters.graph_search_agent_adapter.get_lifecycle_manager",
            return_value=lifecycle_manager,
        ),
        patch(
            "src.infrastructure.llm.adapters.graph_search_agent_adapter.build_graph_search_tools",
            return_value=[lambda variable_id: []],
        ) as build_tools_mock,
        patch(
            "src.infrastructure.llm.adapters.graph_search_agent_adapter.create_graph_search_pipeline",
            return_value=mock_pipeline,
        ) as create_pipeline_mock,
    ):
        adapter = FlujoGraphSearchAdapter(graph_query_service=graph_query_service)
        context = GraphSearchContext(
            question="Find MED13 signals",
            research_space_id="space-tools",
        )
        pipeline = adapter._get_or_create_pipeline(
            "openai:gpt-4o-mini",
            context=context,
        )

    assert pipeline is mock_pipeline
    build_tools_mock.assert_called_once()
    create_pipeline_mock.assert_called_once()
    called_kwargs = create_pipeline_mock.call_args.kwargs
    assert called_kwargs["tools"] is not None
