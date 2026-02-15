"""Tests for Flujo content-enrichment adapter fallback and tool binding behavior."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.domain.agents.contexts.content_enrichment_context import (
    ContentEnrichmentContext,
)
from src.infrastructure.llm.adapters.content_enrichment_agent_adapter import (
    FlujoContentEnrichmentAdapter,
)


def _build_adapter() -> FlujoContentEnrichmentAdapter:
    with (
        patch(
            "src.infrastructure.llm.adapters.content_enrichment_agent_adapter.get_state_backend",
            return_value=MagicMock(),
        ),
        patch(
            "src.infrastructure.llm.adapters.content_enrichment_agent_adapter.get_model_registry",
            return_value=MagicMock(),
        ),
        patch(
            "src.infrastructure.llm.adapters.content_enrichment_agent_adapter.get_lifecycle_manager",
            return_value=MagicMock(),
        ),
    ):
        return FlujoContentEnrichmentAdapter()


@pytest.mark.asyncio
async def test_enrich_falls_back_when_openai_key_missing() -> None:
    adapter = _build_adapter()
    context = ContentEnrichmentContext(
        document_id="doc-1",
        source_type="pubmed",
        external_record_id="PMID123",
        existing_metadata={"raw_record": {"abstract": "Abstract text"}},
    )

    with patch.object(
        FlujoContentEnrichmentAdapter,
        "_has_openai_key",
        return_value=False,
    ):
        contract = await adapter.enrich(context)

    assert contract.decision == "enriched"
    assert contract.acquisition_method == "pass_through"
    assert "API key is not configured" in (contract.warning or "")


@pytest.mark.asyncio
async def test_enrich_uses_pass_through_for_structured_source_types() -> None:
    adapter = _build_adapter()
    context = ContentEnrichmentContext(
        document_id="doc-2",
        source_type="clinvar",
        external_record_id="VCV1",
        existing_metadata={"raw_record": {"clinical_significance": "Pathogenic"}},
    )

    contract = await adapter.enrich(context)
    assert contract.decision == "enriched"
    assert contract.acquisition_method == "pass_through"
    assert contract.content_payload is not None


def test_get_or_create_pipeline_binds_content_enrichment_tools() -> None:
    mock_pipeline = MagicMock()
    lifecycle_manager = MagicMock()

    with (
        patch(
            "src.infrastructure.llm.adapters.content_enrichment_agent_adapter.get_state_backend",
            return_value=MagicMock(),
        ),
        patch(
            "src.infrastructure.llm.adapters.content_enrichment_agent_adapter.get_model_registry",
            return_value=MagicMock(),
        ),
        patch(
            "src.infrastructure.llm.adapters.content_enrichment_agent_adapter.get_lifecycle_manager",
            return_value=lifecycle_manager,
        ),
        patch(
            "src.infrastructure.llm.adapters.content_enrichment_agent_adapter.build_content_enrichment_tools",
            return_value=[lambda pmcid: {"found": False}],
        ) as build_tools_mock,
        patch(
            "src.infrastructure.llm.adapters.content_enrichment_agent_adapter.create_content_enrichment_pipeline",
            return_value=mock_pipeline,
        ) as create_pipeline_mock,
    ):
        adapter = FlujoContentEnrichmentAdapter()
        pipeline = adapter._get_or_create_pipeline("openai:gpt-4o-mini")

    assert pipeline is mock_pipeline
    build_tools_mock.assert_called_once()
    create_pipeline_mock.assert_called_once()
    assert create_pipeline_mock.call_args.kwargs["tools"] is not None
