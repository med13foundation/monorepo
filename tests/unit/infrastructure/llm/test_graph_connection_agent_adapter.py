"""Tests for Flujo graph-connection adapter fallback and tool wiring behavior."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.domain.agents.contexts.graph_connection_context import GraphConnectionContext
from src.infrastructure.llm.adapters.graph_connection_agent_adapter import (
    FlujoGraphConnectionAdapter,
)


def _build_adapter() -> FlujoGraphConnectionAdapter:
    with (
        patch(
            "src.infrastructure.llm.adapters.graph_connection_agent_adapter.get_state_backend",
            return_value=MagicMock(),
        ),
        patch(
            "src.infrastructure.llm.adapters.graph_connection_agent_adapter.get_model_registry",
            return_value=MagicMock(),
        ),
        patch(
            "src.infrastructure.llm.adapters.graph_connection_agent_adapter.get_lifecycle_manager",
            return_value=MagicMock(),
        ),
    ):
        return FlujoGraphConnectionAdapter()


@pytest.mark.asyncio
async def test_discover_escalates_for_unsupported_source() -> None:
    adapter = _build_adapter()
    context = GraphConnectionContext(
        seed_entity_id="entity-1",
        source_type="unsupported_source",
        research_space_id="space-1",
    )

    contract = await adapter.discover(context)

    assert contract.decision == "escalate"
    assert contract.confidence_score == 0.0
    assert "not supported" in contract.rationale


@pytest.mark.asyncio
async def test_discover_uses_heuristic_fallback_without_openai_key() -> None:
    adapter = _build_adapter()
    context = GraphConnectionContext(
        seed_entity_id="entity-2",
        source_type="clinvar",
        research_space_id="space-1",
    )

    with patch.object(
        FlujoGraphConnectionAdapter,
        "_has_openai_key",
        return_value=False,
    ):
        contract = await adapter.discover(context)

    assert contract.decision == "fallback"
    assert contract.seed_entity_id == "entity-2"
    assert contract.proposed_relations == []


def test_get_or_create_pipeline_binds_graph_tools() -> None:
    mock_pipeline = MagicMock()
    lifecycle_manager = MagicMock()
    dictionary_service = MagicMock()
    graph_query_service = MagicMock()
    relation_repository = MagicMock()
    pubmed_factory = MagicMock(return_value=MagicMock(name="unused_pubmed_pipeline"))
    clinvar_factory = MagicMock(return_value=mock_pipeline)

    with (
        patch(
            "src.infrastructure.llm.adapters.graph_connection_agent_adapter.get_state_backend",
            return_value=MagicMock(),
        ),
        patch(
            "src.infrastructure.llm.adapters.graph_connection_agent_adapter.get_model_registry",
            return_value=MagicMock(),
        ),
        patch(
            "src.infrastructure.llm.adapters.graph_connection_agent_adapter.get_lifecycle_manager",
            return_value=lifecycle_manager,
        ),
        patch(
            "src.infrastructure.llm.adapters.graph_connection_agent_adapter.build_graph_connection_tools",
            return_value=[lambda entity_id: entity_id],
        ) as build_tools_mock,
        patch.dict(
            "src.infrastructure.llm.adapters.graph_connection_agent_adapter._PIPELINE_FACTORIES",
            {"clinvar": clinvar_factory, "pubmed": pubmed_factory},
        ),
    ):
        adapter = FlujoGraphConnectionAdapter(
            dictionary_service=dictionary_service,
            graph_query_service=graph_query_service,
            relation_repository=relation_repository,
        )
        context = GraphConnectionContext(
            seed_entity_id="entity-tools",
            source_type="clinvar",
            research_space_id="space-tools",
        )
        pipeline = adapter._get_or_create_pipeline(
            "openai:gpt-4o-mini",
            context=context,
        )

    assert pipeline is mock_pipeline
    build_tools_mock.assert_called_once()
    clinvar_factory.assert_called_once()
    called_kwargs = clinvar_factory.call_args.kwargs
    assert called_kwargs["tools"] is not None


def test_get_or_create_pipeline_dispatches_pubmed_factory() -> None:
    mock_pipeline = MagicMock(name="pubmed_pipeline")
    lifecycle_manager = MagicMock()
    clinvar_factory = MagicMock(return_value=MagicMock(name="unused_clinvar_pipeline"))
    pubmed_factory = MagicMock(return_value=mock_pipeline)

    with (
        patch(
            "src.infrastructure.llm.adapters.graph_connection_agent_adapter.get_state_backend",
            return_value=MagicMock(),
        ),
        patch(
            "src.infrastructure.llm.adapters.graph_connection_agent_adapter.get_model_registry",
            return_value=MagicMock(),
        ),
        patch(
            "src.infrastructure.llm.adapters.graph_connection_agent_adapter.get_lifecycle_manager",
            return_value=lifecycle_manager,
        ),
        patch.dict(
            "src.infrastructure.llm.adapters.graph_connection_agent_adapter._PIPELINE_FACTORIES",
            {"clinvar": clinvar_factory, "pubmed": pubmed_factory},
        ),
    ):
        adapter = FlujoGraphConnectionAdapter(
            dictionary_service=MagicMock(),
            graph_query_service=MagicMock(),
            relation_repository=MagicMock(),
        )
        context = GraphConnectionContext(
            seed_entity_id="entity-tools-pubmed",
            source_type="pubmed",
            research_space_id="space-tools",
        )
        pipeline = adapter._get_or_create_pipeline(
            "openai:gpt-4o-mini",
            context=context,
        )

    assert pipeline is mock_pipeline
    pubmed_factory.assert_called_once()
