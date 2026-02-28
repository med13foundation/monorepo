"""Tests for Artana mapping-judge adapter behavior."""

from __future__ import annotations

import os
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.domain.agents.contexts.mapping_judge_context import MappingJudgeContext
from src.domain.agents.contracts.mapping_judge import (
    MappingJudgeCandidate,
    MappingJudgeContract,
)
from src.domain.agents.models import ModelCapability, ModelSpec
from src.infrastructure.llm.adapters.mapping_judge_agent_adapter import (
    ArtanaMappingJudgeAdapter,
)

_ADAPTER_MODULE = "src.infrastructure.llm.adapters.mapping_judge_agent_adapter"


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
    step_output: MappingJudgeContract | None = None,
):
    registry = _build_registry()
    governance = MagicMock()
    governance.usage_limits.total_cost_usd = 1.0
    governance.usage_limits.max_turns = 5
    governance.usage_limits.max_tokens = 1024

    if step_output is None:
        step_output = MappingJudgeContract(
            decision="matched",
            selected_variable_id="VAR_CARDIOMEGALY_MARKER",
            candidate_count=1,
            selection_rationale="Strong lexical and semantic match.",
            selected_candidate=None,
            confidence_score=0.9,
            rationale="Best candidate match.",
            evidence=[],
            agent_run_id=None,
        )

    client = MagicMock()
    client.step = AsyncMock(return_value=SimpleNamespace(output=step_output))
    kernel = MagicMock()
    kernel.close = AsyncMock()
    model_port = MagicMock()
    model_port.aclose = AsyncMock()

    with (
        patch(f"{_ADAPTER_MODULE}._ARTANA_IMPORT_ERROR", None),
        patch(f"{_ADAPTER_MODULE}.get_model_registry", return_value=registry),
        patch(
            f"{_ADAPTER_MODULE}.GovernanceConfig.from_environment",
            return_value=governance,
        ),
        patch.object(ArtanaMappingJudgeAdapter, "_create_store", return_value=object()),
        patch.object(
            ArtanaMappingJudgeAdapter,
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
        yield ArtanaMappingJudgeAdapter(), client, kernel, model_port


def test_judge_falls_back_when_openai_key_missing() -> None:
    context = _build_context()
    with (
        patch.dict(os.environ, {}, clear=True),
        _build_adapter() as (adapter, client, _, _),
        pytest.raises(RuntimeError, match="requires OPENAI_API_KEY"),
    ):
        adapter.judge(context)
    client.step.assert_not_awaited()


def test_judge_returns_normalized_match_and_run_id() -> None:
    context = _build_context()
    with (
        patch.dict(os.environ, {"OPENAI_API_KEY": "test-openai-key"}, clear=True),
        _build_adapter() as (adapter, client, _, _),
    ):
        contract = adapter.judge(context)

    assert contract.decision == "matched"
    assert contract.selected_variable_id == "VAR_CARDIOMEGALY_MARKER"
    assert contract.selected_candidate is not None
    assert contract.selected_candidate.variable_id == "VAR_CARDIOMEGALY_MARKER"
    assert contract.candidate_count == 1
    assert contract.agent_run_id is not None
    assert contract.agent_run_id.startswith("mapping_judge:")
    client.step.assert_awaited_once()


def test_judge_invalid_selected_id_converts_to_no_match() -> None:
    context = _build_context()
    invalid_output = MappingJudgeContract(
        decision="matched",
        selected_variable_id="VAR_DOES_NOT_EXIST",
        candidate_count=999,
        selection_rationale="Selected hidden candidate.",
        selected_candidate=None,
        confidence_score=0.95,
        rationale="Model hallucinated candidate id.",
        evidence=[],
        agent_run_id=None,
    )

    with (
        patch.dict(os.environ, {"OPENAI_API_KEY": "test-openai-key"}, clear=True),
        _build_adapter(step_output=invalid_output) as (adapter, _, _, _),
        pytest.raises(
            ValueError,
            match="outside provided candidates",
        ),
    ):
        adapter.judge(context)


def test_close_closes_kernel_and_model_port() -> None:
    with _build_adapter() as (adapter, _, kernel, model_port):
        adapter.close()
    kernel.close.assert_awaited_once()
    model_port.aclose.assert_awaited_once()
