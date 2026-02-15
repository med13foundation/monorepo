"""Tests for Flujo mapping-judge adapter fallback and pipeline wiring."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from src.domain.agents.contexts.mapping_judge_context import MappingJudgeContext
from src.domain.agents.contracts.mapping_judge import MappingJudgeCandidate
from src.infrastructure.llm.adapters.mapping_judge_agent_adapter import (
    FlujoMappingJudgeAdapter,
)


def _build_context() -> MappingJudgeContext:
    return MappingJudgeContext(
        field_key="cardiomegaly markr",
        field_value_preview="true",
        source_id="source-1",
        source_type="pubmed",
        domain_context="clinical",
        record_metadata={"entity_type": "PUBLICATION"},
        candidates=[
            MappingJudgeCandidate(
                variable_id="VAR_CARDIOMEGALY_MARKER",
                display_name="Cardiomegaly Marker",
                match_method="fuzzy",
                similarity_score=0.62,
                description="Marker for cardiomegaly",
                metadata={},
            ),
        ],
    )


def _build_adapter() -> FlujoMappingJudgeAdapter:
    with (
        patch(
            "src.infrastructure.llm.adapters.mapping_judge_agent_adapter.get_state_backend",
            return_value=MagicMock(),
        ),
        patch(
            "src.infrastructure.llm.adapters.mapping_judge_agent_adapter.get_model_registry",
            return_value=MagicMock(),
        ),
        patch(
            "src.infrastructure.llm.adapters.mapping_judge_agent_adapter.get_lifecycle_manager",
            return_value=MagicMock(),
        ),
    ):
        return FlujoMappingJudgeAdapter()


def test_judge_falls_back_when_openai_key_missing() -> None:
    adapter = _build_adapter()
    context = _build_context()

    with patch.object(
        FlujoMappingJudgeAdapter,
        "_has_openai_key",
        return_value=False,
    ):
        contract = adapter.judge(context)

    assert contract.decision == "no_match"
    assert contract.selected_variable_id is None
    assert "API key is not configured" in contract.selection_rationale


def test_get_or_create_pipeline_builds_mapping_judge_pipeline() -> None:
    mock_pipeline = MagicMock()
    lifecycle_manager = MagicMock()

    with (
        patch(
            "src.infrastructure.llm.adapters.mapping_judge_agent_adapter.get_state_backend",
            return_value=MagicMock(),
        ),
        patch(
            "src.infrastructure.llm.adapters.mapping_judge_agent_adapter.get_model_registry",
            return_value=MagicMock(),
        ),
        patch(
            "src.infrastructure.llm.adapters.mapping_judge_agent_adapter.get_lifecycle_manager",
            return_value=lifecycle_manager,
        ),
        patch(
            "src.infrastructure.llm.adapters.mapping_judge_agent_adapter.create_mapping_judge_pipeline",
            return_value=mock_pipeline,
        ) as create_pipeline_mock,
    ):
        adapter = FlujoMappingJudgeAdapter()
        pipeline = adapter._get_or_create_pipeline("openai:gpt-4o-mini")

    assert pipeline is mock_pipeline
    create_pipeline_mock.assert_called_once()
