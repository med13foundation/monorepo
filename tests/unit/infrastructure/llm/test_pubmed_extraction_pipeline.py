"""Tests for PubMed extraction pipeline registration."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from src.infrastructure.llm.factories.extraction_agent_factory import (
    get_extraction_system_prompt,
)
from src.infrastructure.llm.pipelines.extraction_pipelines.pubmed_pipeline import (
    create_pubmed_extraction_pipeline,
)


def test_pubmed_extraction_prompt_is_pubmed_specific() -> None:
    prompt = get_extraction_system_prompt("pubmed")
    assert "PubMed" in prompt
    assert 'source_type must be "pubmed"' in prompt
    assert "ClinVar records" not in prompt


def test_create_pubmed_extraction_pipeline_has_pubmed_stage_steps() -> None:
    with patch(
        "src.infrastructure.llm.factories.extraction_agent_factory.make_agent_async",
        return_value=MagicMock(name="agent"),
    ):
        pipeline = create_pubmed_extraction_pipeline(state_backend=MagicMock())

    assert pipeline.pipeline is not None
    step_names = [step.name for step in pipeline.pipeline.steps]
    assert "discover_pubmed_extraction_candidates" in step_names
    assert "prepare_pubmed_extraction_synthesis_input" in step_names
    assert "synthesize_pubmed_extraction_contract" in step_names
