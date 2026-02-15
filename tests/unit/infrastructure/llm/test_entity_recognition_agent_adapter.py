"""Tests for Flujo entity-recognition adapter fallback behavior."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.domain.agents.contexts.entity_recognition_context import (
    EntityRecognitionContext,
)
from src.infrastructure.llm.adapters.entity_recognition_agent_adapter import (
    FlujoEntityRecognitionAdapter,
)


def _build_adapter() -> FlujoEntityRecognitionAdapter:
    with (
        patch(
            "src.infrastructure.llm.adapters.entity_recognition_agent_adapter.get_state_backend",
            return_value=MagicMock(),
        ),
        patch(
            "src.infrastructure.llm.adapters.entity_recognition_agent_adapter.get_model_registry",
            return_value=MagicMock(),
        ),
        patch(
            "src.infrastructure.llm.adapters.entity_recognition_agent_adapter.get_lifecycle_manager",
            return_value=MagicMock(),
        ),
    ):
        return FlujoEntityRecognitionAdapter()


@pytest.mark.asyncio
async def test_recognize_escalates_for_unsupported_source() -> None:
    adapter = _build_adapter()
    context = EntityRecognitionContext(
        document_id="doc-1",
        source_type="pubmed",
        raw_record={"title": "Example"},
    )

    contract = await adapter.recognize(context)

    assert contract.decision == "escalate"
    assert contract.confidence_score == 0.0
    assert "not supported" in contract.rationale


@pytest.mark.asyncio
async def test_recognize_uses_heuristic_fallback_without_openai_key() -> None:
    adapter = _build_adapter()
    context = EntityRecognitionContext(
        document_id="doc-2",
        source_type="clinvar",
        raw_record={
            "clinvar_id": "1234",
            "gene_symbol": "MED13",
            "condition": "Intellectual disability",
            "clinical_significance": "pathogenic",
        },
    )

    with patch.object(
        FlujoEntityRecognitionAdapter,
        "_has_openai_key",
        return_value=False,
    ):
        contract = await adapter.recognize(context)

    assert contract.decision == "generated"
    assert contract.recognized_entities
    assert contract.pipeline_payloads
    assert contract.primary_entity_type == "VARIANT"


@pytest.mark.asyncio
async def test_recognize_returns_fallback_when_no_entities_detected() -> None:
    adapter = _build_adapter()
    context = EntityRecognitionContext(
        document_id="doc-3",
        source_type="clinvar",
        raw_record={},
    )

    with patch.object(
        FlujoEntityRecognitionAdapter,
        "_has_openai_key",
        return_value=False,
    ):
        contract = await adapter.recognize(context)

    assert contract.decision == "fallback"
    assert contract.recognized_entities == []


def test_get_or_create_pipeline_binds_dictionary_tools() -> None:
    dictionary_service = MagicMock()
    mock_pipeline = MagicMock()
    lifecycle_manager = MagicMock()
    mock_registry = MagicMock()
    mock_registry.validate_model_for_capability.return_value = True

    with (
        patch(
            "src.infrastructure.llm.adapters.entity_recognition_agent_adapter.get_state_backend",
            return_value=MagicMock(),
        ),
        patch(
            "src.infrastructure.llm.adapters.entity_recognition_agent_adapter.get_model_registry",
            return_value=mock_registry,
        ),
        patch(
            "src.infrastructure.llm.adapters.entity_recognition_agent_adapter.get_lifecycle_manager",
            return_value=lifecycle_manager,
        ),
        patch(
            "src.infrastructure.llm.adapters.entity_recognition_agent_adapter.build_entity_recognition_dictionary_tools",
            return_value=[lambda terms: terms],
        ) as build_tools_mock,
        patch(
            "src.infrastructure.llm.adapters.entity_recognition_agent_adapter.create_clinvar_entity_recognition_pipeline",
            return_value=mock_pipeline,
        ) as create_pipeline_mock,
    ):
        adapter = FlujoEntityRecognitionAdapter(dictionary_service=dictionary_service)
        context = EntityRecognitionContext(
            document_id="doc-tools",
            source_type="clinvar",
            research_space_settings={
                "dictionary_agent_creation_policy": "PENDING_REVIEW",
            },
            raw_record={"field": "value"},
        )
        pipeline = adapter._get_or_create_pipeline(
            "openai:gpt-4o-mini",
            policy_key="PENDING_REVIEW",
            context=context,
        )

    assert pipeline is mock_pipeline
    build_tools_mock.assert_called_once()
    create_pipeline_mock.assert_called_once()
    called_kwargs = create_pipeline_mock.call_args.kwargs
    assert called_kwargs["tools"] is not None
