"""Tests for Artana content-enrichment adapter behavior."""

from __future__ import annotations

import os
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.domain.agents.contexts.content_enrichment_context import (
    ContentEnrichmentContext,
)
from src.domain.agents.contracts.content_enrichment import ContentEnrichmentContract
from src.domain.agents.models import ModelCapability, ModelSpec
from src.infrastructure.llm.adapters.content_enrichment_agent_adapter import (
    ArtanaContentEnrichmentAdapter,
)

_ADAPTER_MODULE = "src.infrastructure.llm.adapters.content_enrichment_agent_adapter"


def _build_registry() -> MagicMock:
    registry = MagicMock()
    model_spec = ModelSpec(
        model_id="openai:gpt-5-mini",
        display_name="GPT-5 Mini",
        provider="openai",
        capabilities=frozenset({ModelCapability.EVIDENCE_EXTRACTION}),
        prompt_tokens_per_1k=0.00025,
        completion_tokens_per_1k=0.002,
        timeout_seconds=120.0,
        is_default=True,
    )
    registry.get_model.return_value = model_spec
    registry.get_default_model.return_value = model_spec
    registry.allow_runtime_model_overrides.return_value = True
    registry.validate_model_for_capability.return_value = True
    return registry


@contextmanager
def _build_adapter(
    *,
    step_output: ContentEnrichmentContract | None = None,
):
    if step_output is None:
        step_output = ContentEnrichmentContract(
            decision="enriched",
            confidence_score=0.85,
            rationale="Full text was enriched through OA acquisition.",
            evidence=[],
            document_id="doc-1",
            source_type="pubmed",
            acquisition_method="pmc_oa",
            content_format="text",
            content_length_chars=42,
            content_text="Sample enriched full-text payload.",
            content_payload={"content": "Sample enriched full-text payload."},
            warning=None,
            agent_run_id="content_enrichment:pubmed:doc-1",
        )

    governance = MagicMock()
    governance.usage_limits.total_cost_usd = 1.0
    governance.usage_limits.max_turns = 8
    governance.usage_limits.max_tokens = 4096

    client = MagicMock()
    client.step = AsyncMock(return_value=SimpleNamespace(output=step_output))
    kernel = MagicMock()
    kernel.close = AsyncMock()
    model_port = MagicMock()
    model_port.aclose = AsyncMock()

    with (
        patch(f"{_ADAPTER_MODULE}._ARTANA_IMPORT_ERROR", None),
        patch(f"{_ADAPTER_MODULE}.get_model_registry", return_value=_build_registry()),
        patch(
            f"{_ADAPTER_MODULE}.GovernanceConfig.from_environment",
            return_value=governance,
        ),
        patch.object(
            ArtanaContentEnrichmentAdapter,
            "_create_store",
            return_value=object(),
        ),
        patch.object(
            ArtanaContentEnrichmentAdapter,
            "_create_tenant",
            return_value=object(),
        ),
        patch(f"{_ADAPTER_MODULE}._OpenAIChatModelPort", return_value=model_port),
        patch(f"{_ADAPTER_MODULE}.ArtanaKernel", return_value=kernel, create=True),
        patch(
            f"{_ADAPTER_MODULE}.SingleStepModelClient",
            return_value=client,
            create=True,
        ),
    ):
        yield ArtanaContentEnrichmentAdapter(), client, kernel, model_port


@pytest.mark.asyncio
async def test_enrich_falls_back_when_openai_key_missing() -> None:
    with (
        patch.dict(os.environ, {}, clear=True),
        _build_adapter() as (adapter, client, _, _),
    ):
        context = ContentEnrichmentContext(
            document_id="doc-1",
            source_type="pubmed",
            external_record_id="PMID123",
            existing_metadata={"raw_record": {"abstract": "Abstract text"}},
        )
        contract = await adapter.enrich(context)

    assert contract.decision == "failed"
    assert contract.acquisition_method == "skipped"
    assert "missing_openai_api_key" in (contract.warning or "")
    client.step.assert_not_awaited()


@pytest.mark.asyncio
async def test_enrich_uses_pass_through_for_structured_source_types() -> None:
    with _build_adapter() as (adapter, client, _, _):
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
    client.step.assert_not_awaited()


@pytest.mark.asyncio
async def test_enrich_executes_artana_step_for_unstructured_sources() -> None:
    with (
        patch.dict(os.environ, {"OPENAI_API_KEY": "test-openai-key"}, clear=True),
        _build_adapter() as (adapter, client, _, _),
    ):
        context = ContentEnrichmentContext(
            document_id="doc-3",
            source_type="pubmed",
            external_record_id="PMID999",
            existing_metadata={
                "raw_record": {"abstract": "Potential full text enrichment"},
            },
            research_space_id="space-1",
        )
        contract = await adapter.enrich(context)

    assert contract.decision == "enriched"
    assert contract.acquisition_method == "pmc_oa"
    assert contract.document_id == "doc-3"
    assert contract.source_type == "pubmed"
    assert contract.agent_run_id is not None
    assert contract.agent_run_id.startswith("content_enrichment:pubmed:")
    client.step.assert_awaited_once()


@pytest.mark.asyncio
async def test_close_closes_kernel_and_model_port() -> None:
    with _build_adapter() as (adapter, _, kernel, model_port):
        await adapter.close()
    kernel.close.assert_awaited_once()
    model_port.aclose.assert_awaited_once()
