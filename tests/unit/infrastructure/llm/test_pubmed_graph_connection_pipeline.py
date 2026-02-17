"""Tests for PubMed graph-connection pipeline registration."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from src.infrastructure.llm.factories.graph_connection_agent_factory import (
    get_graph_connection_system_prompt,
)
from src.infrastructure.llm.pipelines.graph_connection_pipelines.pubmed_pipeline import (
    create_pubmed_graph_connection_pipeline,
)


def test_pubmed_graph_connection_prompt_is_pubmed_specific() -> None:
    prompt = get_graph_connection_system_prompt("pubmed")
    assert "PubMed" in prompt
    assert 'source_type must be "pubmed"' in prompt
    assert "ClinVar-backed research spaces" not in prompt


def test_create_pubmed_graph_connection_pipeline_has_pubmed_subagent_steps() -> None:
    with patch(
        "src.infrastructure.llm.factories.graph_connection_agent_factory.make_agent_async",
        return_value=MagicMock(name="agent"),
    ):
        pipeline = create_pubmed_graph_connection_pipeline(state_backend=MagicMock())

    assert pipeline.pipeline is not None
    step_names = [step.name for step in pipeline.pipeline.steps]
    assert "discover_pubmed_graph_connection_candidates" in step_names
    assert "synthesize_pubmed_graph_connections" in step_names
    assert step_names.index(
        "discover_pubmed_graph_connection_candidates",
    ) < step_names.index(
        "synthesize_pubmed_graph_connections",
    )
