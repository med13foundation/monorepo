"""Tests for Artana extraction adapter behavior."""

from __future__ import annotations

import os
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.domain.agents.contexts.extraction_context import ExtractionContext
from src.domain.agents.contracts.extraction import ExtractionContract
from src.domain.agents.models import ModelCapability, ModelSpec
from src.graph.domain_biomedical.extraction_payload import (
    BIOMEDICAL_EXTRACTION_PAYLOAD_CONFIG,
)
from src.graph.domain_biomedical.extraction_prompt import (
    BIOMEDICAL_EXTRACTION_PROMPT_CONFIG,
)
from src.infrastructure.llm.adapters.extraction_agent_adapter import (
    ArtanaExtractionAdapter,
)

_ADAPTER_MODULE = "src.infrastructure.llm.adapters.extraction_agent_adapter"


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
    step_output: ExtractionContract | None = None,
):
    if step_output is None:
        step_output = ExtractionContract(
            decision="generated",
            confidence_score=0.88,
            rationale="Extracted relations and observations from source.",
            evidence=[],
            source_type="pubmed",
            document_id="doc-1",
            observations=[],
            relations=[],
            rejected_facts=[],
            pipeline_payloads=[],
            shadow_mode=True,
            agent_run_id=None,
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
        patch.object(ArtanaExtractionAdapter, "_create_store", return_value=object()),
        patch.object(ArtanaExtractionAdapter, "_create_tenant", return_value=object()),
        patch(f"{_ADAPTER_MODULE}._OpenAIChatModelPort", return_value=model_port),
        patch(f"{_ADAPTER_MODULE}.ArtanaKernel", return_value=kernel, create=True),
        patch(
            f"{_ADAPTER_MODULE}.SingleStepModelClient",
            return_value=client,
            create=True,
        ),
    ):
        yield (
            ArtanaExtractionAdapter(
                prompt_config=BIOMEDICAL_EXTRACTION_PROMPT_CONFIG,
                payload_config=BIOMEDICAL_EXTRACTION_PAYLOAD_CONFIG,
            ),
            client,
            kernel,
            model_port,
        )


@pytest.mark.asyncio
async def test_extract_escalates_for_unsupported_source() -> None:
    with _build_adapter() as (adapter, client, _, _):
        context = ExtractionContext(
            document_id="doc-1",
            source_type="unsupported_source",
            raw_record={"title": "Example"},
        )

        contract = await adapter.extract(context)

    assert contract.decision == "escalate"
    assert contract.confidence_score == 0.0
    assert "not supported" in contract.rationale
    client.step.assert_not_awaited()


@pytest.mark.asyncio
async def test_extract_escalates_without_openai_key() -> None:
    with (
        patch.dict(os.environ, {}, clear=True),
        _build_adapter() as (adapter, client, _, _),
    ):
        context = ExtractionContext(
            document_id="doc-2",
            source_type="clinvar",
            raw_record={"clinical_significance": "pathogenic"},
            recognized_observations=[],
        )
        contract = await adapter.extract(context)

    assert contract.decision == "escalate"
    assert contract.pipeline_payloads == []
    assert contract.observations == []
    assert "AI-only extraction is required" in contract.rationale
    client.step.assert_not_awaited()


@pytest.mark.asyncio
async def test_extract_normalizes_source_document_and_payloads() -> None:
    with (
        patch.dict(os.environ, {"OPENAI_API_KEY": "test-openai-key"}, clear=True),
        _build_adapter() as (adapter, client, kernel, model_port),
    ):
        context = ExtractionContext(
            document_id="doc-3",
            source_type="PUBMED",
            raw_record={
                "pubmed_id": "12345",
                "title": "MED13 impacts transcription",
                "abstract": "MED13 interacts with mediator subunits.",
            },
            shadow_mode=False,
        )
        contract = await adapter.extract(context)

    assert contract.decision == "generated"
    assert contract.source_type == "pubmed"
    assert contract.document_id == "doc-3"
    assert contract.shadow_mode is False
    assert contract.pipeline_payloads
    assert contract.agent_run_id is not None
    assert contract.agent_run_id.startswith("extraction:pubmed:")
    client.step.assert_awaited_once()
    kernel.close.assert_awaited_once()
    model_port.aclose.assert_awaited_once()


@pytest.mark.asyncio
async def test_close_is_noop() -> None:
    with _build_adapter() as (adapter, _, kernel, model_port):
        await adapter.close()
    kernel.close.assert_not_awaited()
    model_port.aclose.assert_not_awaited()


def test_get_system_prompt_uses_pack_prompt_dispatch() -> None:
    with _build_adapter() as (adapter, _client, _kernel, _model_port):
        prompt = adapter._get_system_prompt("clinvar")

    assert "ClinVar records" in prompt


def test_get_system_prompt_rejects_unsupported_source() -> None:
    with (
        _build_adapter() as (adapter, _client, _kernel, _model_port),
        pytest.raises(
            ValueError,
            match="Unsupported extraction source type: unsupported",
        ),
    ):
        adapter._get_system_prompt("unsupported")


def test_build_compact_raw_record_uses_pack_pubmed_rules() -> None:
    context = ExtractionContext(
        document_id="doc-compact-pubmed",
        source_type="pubmed",
        raw_record={
            "pubmed_id": "12345",
            "title": "MED13 impacts transcription",
            "abstract": "Abstract content",
            "ignored_field": "ignored",
        },
    )

    with _build_adapter() as (adapter, _client, _kernel, _model_port):
        compact = adapter._build_compact_raw_record(context)

    assert compact == {
        "pubmed_id": "12345",
        "title": "MED13 impacts transcription",
        "abstract": "Abstract content",
    }


def test_build_compact_raw_record_uses_pack_pubmed_chunk_rules() -> None:
    context = ExtractionContext(
        document_id="doc-compact-pubmed-chunk",
        source_type="pubmed",
        raw_record={
            "pubmed_id": "12345",
            "title": "MED13 impacts transcription",
            "full_text": "Chunk text",
            "full_text_chunk_index": 1,
            "full_text_chunk_total": 3,
            "journal": "Ignored in chunk mode",
        },
    )

    with _build_adapter() as (adapter, _client, _kernel, _model_port):
        compact = adapter._build_compact_raw_record(context)

    assert compact == {
        "pubmed_id": "12345",
        "title": "MED13 impacts transcription",
        "full_text": "Chunk text",
        "full_text_chunk_index": 1,
        "full_text_chunk_total": 3,
    }


def test_build_compact_raw_record_uses_pack_clinvar_rules() -> None:
    context = ExtractionContext(
        document_id="doc-compact-clinvar",
        source_type="clinvar",
        raw_record={
            "variation_id": "1234",
            "gene_symbol": "MED13",
            "clinical_significance": "pathogenic",
            "ignored_field": "ignored",
        },
    )

    with _build_adapter() as (adapter, _client, _kernel, _model_port):
        compact = adapter._build_compact_raw_record(context)

    assert compact == {
        "variation_id": "1234",
        "gene_symbol": "MED13",
        "clinical_significance": "pathogenic",
    }
