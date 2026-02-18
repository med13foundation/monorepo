"""Tests for PubMed entity-recognition pipeline registration."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from src.infrastructure.llm.factories.entity_recognition_agent_factory import (
    get_entity_recognition_system_prompt,
)
from src.infrastructure.llm.pipelines.entity_recognition_pipelines.pubmed_pipeline import (
    create_pubmed_entity_recognition_pipeline,
)


def test_pubmed_entity_recognition_prompt_is_pubmed_specific() -> None:
    prompt = get_entity_recognition_system_prompt("pubmed")
    assert "PubMed" in prompt
    assert 'source_type must be "pubmed"' in prompt
    assert "ClinVar records" not in prompt


def test_create_pubmed_entity_recognition_pipeline_has_pubmed_step_name() -> None:
    with patch(
        "src.infrastructure.llm.factories.entity_recognition_agent_factory.make_agent_async",
        return_value=MagicMock(name="agent"),
    ):
        pipeline = create_pubmed_entity_recognition_pipeline(state_backend=MagicMock())

    assert pipeline.pipeline is not None
    step_names = [step.name for step in pipeline.pipeline.steps]
    assert "discover_pubmed_entities" in step_names
    assert "entity_recognition_dictionary_policy_gate" in step_names
