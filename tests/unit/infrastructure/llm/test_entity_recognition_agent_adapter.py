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
        source_type="unsupported_source",
        raw_record={"title": "Example"},
    )

    contract = await adapter.recognize(context)

    assert contract.decision == "escalate"
    assert contract.confidence_score == 0.0
    assert "not supported" in contract.rationale


@pytest.mark.asyncio
async def test_recognize_escalates_without_openai_key() -> None:
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

    assert contract.decision == "escalate"
    assert contract.recognized_entities == []
    assert contract.pipeline_payloads == []
    assert "AI-only entity recognition is required" in contract.rationale


@pytest.mark.asyncio
async def test_recognize_escalates_when_no_openai_key_and_empty_input() -> None:
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

    assert contract.decision == "escalate"
    assert contract.recognized_entities == []


def test_get_or_create_pipeline_binds_dictionary_tools() -> None:
    dictionary_service = MagicMock()
    mock_pipeline = MagicMock()
    lifecycle_manager = MagicMock()
    mock_registry = MagicMock()
    mock_registry.validate_model_for_capability.return_value = True
    pubmed_factory = MagicMock(return_value=MagicMock(name="unused_pubmed_pipeline"))
    clinvar_factory = MagicMock(return_value=mock_pipeline)

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
        patch.dict(
            "src.infrastructure.llm.adapters.entity_recognition_agent_adapter._PIPELINE_FACTORIES",
            {"clinvar": clinvar_factory, "pubmed": pubmed_factory},
        ),
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
            source_type="clinvar",
            policy_key="PENDING_REVIEW",
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
    mock_registry = MagicMock()
    mock_registry.validate_model_for_capability.return_value = True
    clinvar_factory = MagicMock(return_value=MagicMock(name="unused_clinvar_pipeline"))
    pubmed_factory = MagicMock(return_value=mock_pipeline)

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
        patch.dict(
            "src.infrastructure.llm.adapters.entity_recognition_agent_adapter._PIPELINE_FACTORIES",
            {"clinvar": clinvar_factory, "pubmed": pubmed_factory},
        ),
    ):
        adapter = FlujoEntityRecognitionAdapter(dictionary_service=MagicMock())
        context = EntityRecognitionContext(
            document_id="doc-tools-pubmed",
            source_type="pubmed",
            raw_record={"title": "PubMed title"},
        )
        pipeline = adapter._get_or_create_pipeline(
            "openai:gpt-4o-mini",
            source_type="pubmed",
            policy_key="DEFAULT",
            context=context,
        )

    assert pipeline is mock_pipeline
    pubmed_factory.assert_called_once()
