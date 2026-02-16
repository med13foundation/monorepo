"""Tests for Flujo extraction adapter fallback and tool wiring behavior."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.domain.agents.contexts.extraction_context import ExtractionContext
from src.infrastructure.llm.adapters.extraction_agent_adapter import (
    FlujoExtractionAdapter,
)


def _build_adapter() -> FlujoExtractionAdapter:
    with (
        patch(
            "src.infrastructure.llm.adapters.extraction_agent_adapter.get_state_backend",
            return_value=MagicMock(),
        ),
        patch(
            "src.infrastructure.llm.adapters.extraction_agent_adapter.get_model_registry",
            return_value=MagicMock(),
        ),
        patch(
            "src.infrastructure.llm.adapters.extraction_agent_adapter.get_lifecycle_manager",
            return_value=MagicMock(),
        ),
    ):
        return FlujoExtractionAdapter()


@pytest.mark.asyncio
async def test_extract_escalates_for_unsupported_source() -> None:
    adapter = _build_adapter()
    context = ExtractionContext(
        document_id="doc-1",
        source_type="unsupported_source",
        raw_record={"title": "Example"},
    )

    contract = await adapter.extract(context)

    assert contract.decision == "escalate"
    assert contract.confidence_score == 0.0
    assert "not supported" in contract.rationale


@pytest.mark.asyncio
async def test_extract_escalates_without_openai_key() -> None:
    adapter = _build_adapter()
    context = ExtractionContext(
        document_id="doc-2",
        source_type="clinvar",
        raw_record={"clinical_significance": "pathogenic"},
        recognized_observations=[],
    )

    with patch.object(
        FlujoExtractionAdapter,
        "_has_openai_key",
        return_value=False,
    ):
        contract = await adapter.extract(context)

    assert contract.decision == "escalate"
    assert contract.pipeline_payloads == []
    assert contract.observations == []
    assert "AI-only extraction is required" in contract.rationale


def test_get_or_create_pipeline_binds_extraction_tools() -> None:
    dictionary_service = MagicMock()
    mock_pipeline = MagicMock()
    lifecycle_manager = MagicMock()
    pubmed_factory = MagicMock(return_value=MagicMock(name="unused_pubmed_pipeline"))
    clinvar_factory = MagicMock(return_value=mock_pipeline)

    with (
        patch(
            "src.infrastructure.llm.adapters.extraction_agent_adapter.get_state_backend",
            return_value=MagicMock(),
        ),
        patch(
            "src.infrastructure.llm.adapters.extraction_agent_adapter.get_model_registry",
            return_value=MagicMock(),
        ),
        patch(
            "src.infrastructure.llm.adapters.extraction_agent_adapter.get_lifecycle_manager",
            return_value=lifecycle_manager,
        ),
        patch(
            "src.infrastructure.llm.adapters.extraction_agent_adapter.build_extraction_validation_tools",
            return_value=[lambda variable_id, value: {"valid": True}],
        ) as build_tools_mock,
        patch.dict(
            "src.infrastructure.llm.adapters.extraction_agent_adapter._PIPELINE_FACTORIES",
            {"clinvar": clinvar_factory, "pubmed": pubmed_factory},
        ),
    ):
        adapter = FlujoExtractionAdapter(dictionary_service=dictionary_service)
        pipeline = adapter._get_or_create_pipeline(
            "openai:gpt-4o-mini",
            source_type="clinvar",
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
            "src.infrastructure.llm.adapters.extraction_agent_adapter.get_state_backend",
            return_value=MagicMock(),
        ),
        patch(
            "src.infrastructure.llm.adapters.extraction_agent_adapter.get_model_registry",
            return_value=MagicMock(),
        ),
        patch(
            "src.infrastructure.llm.adapters.extraction_agent_adapter.get_lifecycle_manager",
            return_value=lifecycle_manager,
        ),
        patch.dict(
            "src.infrastructure.llm.adapters.extraction_agent_adapter._PIPELINE_FACTORIES",
            {"clinvar": clinvar_factory, "pubmed": pubmed_factory},
        ),
    ):
        adapter = FlujoExtractionAdapter(dictionary_service=MagicMock())
        pipeline = adapter._get_or_create_pipeline(
            "openai:gpt-4o-mini",
            source_type="pubmed",
        )

    assert pipeline is mock_pipeline
    pubmed_factory.assert_called_once()
