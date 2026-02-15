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


def test_create_pubmed_extraction_pipeline_has_pubmed_step_name() -> None:
    with patch(
        "src.infrastructure.llm.factories.extraction_agent_factory.make_agent_async",
        return_value=MagicMock(name="agent"),
    ):
        pipeline = create_pubmed_extraction_pipeline(state_backend=MagicMock())

    assert pipeline.pipeline is not None
    step_names = [step.name for step in pipeline.pipeline.steps]
    assert "extract_pubmed_facts" in step_names
