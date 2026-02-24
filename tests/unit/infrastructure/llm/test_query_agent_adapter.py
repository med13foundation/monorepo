"""Tests for ArtanaQueryAgentAdapter behavior."""

from __future__ import annotations

import os
from contextlib import contextmanager
from types import SimpleNamespace
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.domain.agents.contracts.query_generation import QueryGenerationContract
from src.domain.agents.models import ModelCapability, ModelSpec
from src.infrastructure.llm.adapters.query_agent_adapter import ArtanaQueryAgentAdapter
from src.infrastructure.llm.config import QuerySourcePolicy, UsageLimits

_ADAPTER_MODULE = "src.infrastructure.llm.adapters.query_agent_adapter"

if TYPE_CHECKING:
    from collections.abc import Iterator


@pytest.fixture
def mock_model_specs() -> dict[str, ModelSpec]:
    """Create model specs used by registry mocks."""
    return {
        "openai:gpt-5-mini": ModelSpec(
            model_id="openai:gpt-5-mini",
            display_name="GPT-5 Mini",
            provider="openai",
            capabilities=frozenset(
                {
                    ModelCapability.QUERY_GENERATION,
                    ModelCapability.EVIDENCE_EXTRACTION,
                },
            ),
            prompt_tokens_per_1k=0.00025,
            completion_tokens_per_1k=0.002,
            timeout_seconds=120.0,
            is_default=True,
        ),
        "openai:gpt-5-nano": ModelSpec(
            model_id="openai:gpt-5-nano",
            display_name="GPT-5 Nano",
            provider="openai",
            capabilities=frozenset({ModelCapability.QUERY_GENERATION}),
            prompt_tokens_per_1k=0.00005,
            completion_tokens_per_1k=0.0004,
            timeout_seconds=90.0,
        ),
    }


@pytest.fixture
def mock_registry(mock_model_specs: dict[str, ModelSpec]) -> MagicMock:
    """Create a model registry mock compatible with adapter logic."""
    registry = MagicMock()
    registry.get_default_model.return_value = mock_model_specs["openai:gpt-5-mini"]
    registry.get_model.side_effect = lambda model_id: mock_model_specs[model_id]
    registry.validate_model_for_capability.side_effect = (
        lambda model_id, capability: model_id in mock_model_specs
        and capability in mock_model_specs[model_id].capabilities
    )
    registry.allow_runtime_model_overrides.return_value = True
    return registry


@pytest.fixture
def mock_governance() -> MagicMock:
    """Create governance config mock used by adapter."""
    governance = MagicMock()
    governance.usage_limits = UsageLimits(
        total_cost_usd=1.0,
        max_turns=8,
        max_tokens=4096,
    )
    governance.require_evidence = False
    governance.needs_human_review.return_value = False
    return governance


@contextmanager
def create_adapter(
    *,
    mock_registry: MagicMock,
    mock_governance: MagicMock,
    source_policies: dict[str, QuerySourcePolicy] | None = None,
    model: str | None = None,
    step_output: QueryGenerationContract | None = None,
    step_error: Exception | None = None,
) -> Iterator[tuple[ArtanaQueryAgentAdapter, MagicMock, MagicMock, MagicMock]]:
    """
    Build adapter with all external dependencies mocked.

    Returns:
        tuple(adapter, client_mock, kernel_mock, model_port_mock)
    """
    if source_policies is None:
        source_policies = {}
    if step_output is None:
        step_output = QueryGenerationContract(
            decision="generated",
            confidence_score=0.92,
            rationale="Generated query successfully.",
            evidence=[],
            query="MED13[Title/Abstract]",
            source_type="pubmed",
            query_complexity="simple",
        )

    client = MagicMock()
    if step_error is not None:
        client.step = AsyncMock(side_effect=step_error)
    else:
        client.step = AsyncMock(return_value=SimpleNamespace(output=step_output))

    kernel = MagicMock()
    kernel.close = AsyncMock()

    model_port = MagicMock()
    model_port.aclose = AsyncMock()

    with (
        patch(f"{_ADAPTER_MODULE}._ARTANA_IMPORT_ERROR", None),
        patch(f"{_ADAPTER_MODULE}.get_model_registry", return_value=mock_registry),
        patch(
            f"{_ADAPTER_MODULE}.GovernanceConfig.from_environment",
            return_value=mock_governance,
        ),
        patch(
            f"{_ADAPTER_MODULE}.load_query_source_policies",
            return_value=source_policies,
        ),
        patch.object(ArtanaQueryAgentAdapter, "_create_store", return_value=object()),
        patch.object(ArtanaQueryAgentAdapter, "_create_tenant", return_value=object()),
        patch(f"{_ADAPTER_MODULE}._OpenAIChatModelPort", return_value=model_port),
        patch(f"{_ADAPTER_MODULE}.ArtanaKernel", return_value=kernel, create=True),
        patch(
            f"{_ADAPTER_MODULE}.SingleStepModelClient",
            return_value=client,
            create=True,
        ),
    ):
        adapter = ArtanaQueryAgentAdapter(model=model)
        yield adapter, client, kernel, model_port


class TestArtanaQueryAgentAdapter:
    """Tests for model resolution, governance, and execution flow."""

    def test_adapter_initializes_with_default_registry(
        self,
        mock_registry: MagicMock,
        mock_governance: MagicMock,
    ) -> None:
        with create_adapter(
            mock_registry=mock_registry,
            mock_governance=mock_governance,
        ) as (adapter, _, _, _):
            assert adapter._registry is mock_registry

    def test_resolve_model_id_prefers_runtime_override(
        self,
        mock_registry: MagicMock,
        mock_governance: MagicMock,
    ) -> None:
        with create_adapter(
            mock_registry=mock_registry,
            mock_governance=mock_governance,
            model="openai:gpt-5-mini",
        ) as (adapter, _, _, _):
            model_id = adapter._resolve_model_id("pubmed", "openai:gpt-5-nano")
            assert model_id == "openai:gpt-5-nano"

    def test_resolve_model_id_uses_source_policy_fallback(
        self,
        mock_registry: MagicMock,
        mock_governance: MagicMock,
    ) -> None:
        policies = {"clinvar": QuerySourcePolicy(model_id="openai:gpt-5-nano")}
        with create_adapter(
            mock_registry=mock_registry,
            mock_governance=mock_governance,
            source_policies=policies,
            model="openai:gpt-5-mini",
        ) as (adapter, _, _, _):
            model_id = adapter._resolve_model_id("clinvar", None)
            assert model_id == "openai:gpt-5-nano"

    def test_resolve_usage_limits_merges_source_profile_with_governance_defaults(
        self,
        mock_registry: MagicMock,
        mock_governance: MagicMock,
    ) -> None:
        policies = {
            "clinvar": QuerySourcePolicy(
                usage_limits=UsageLimits(
                    total_cost_usd=2.5,
                    max_turns=None,
                    max_tokens=2048,
                ),
            ),
        }
        with create_adapter(
            mock_registry=mock_registry,
            mock_governance=mock_governance,
            source_policies=policies,
        ) as (adapter, _, _, _):
            limits = adapter._resolve_usage_limits("clinvar")
            assert limits.total_cost_usd == 2.5
            assert limits.max_turns == 8
            assert limits.max_tokens == 2048

    @pytest.mark.asyncio
    async def test_generate_query_unsupported_source_returns_escalate(
        self,
        mock_registry: MagicMock,
        mock_governance: MagicMock,
    ) -> None:
        with create_adapter(
            mock_registry=mock_registry,
            mock_governance=mock_governance,
        ) as (adapter, client, _, _):
            result = await adapter.generate_query(
                research_space_description="test",
                user_instructions="test",
                source_type="unsupported-source",
            )
            assert result.decision == "escalate"
            assert "not yet supported" in result.rationale
            client.step.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_generate_query_without_api_key_returns_fallback(
        self,
        mock_registry: MagicMock,
        mock_governance: MagicMock,
    ) -> None:
        with (
            patch.dict(os.environ, {}, clear=True),
            create_adapter(
                mock_registry=mock_registry,
                mock_governance=mock_governance,
            ) as (adapter, client, _, _),
        ):
            result = await adapter.generate_query(
                research_space_description="test",
                user_instructions="test",
                source_type="pubmed",
            )
            assert result.decision == "fallback"
            assert "API key not configured" in result.rationale
            client.step.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_generate_query_success_returns_contract_and_tracks_run_id(
        self,
        mock_registry: MagicMock,
        mock_governance: MagicMock,
    ) -> None:
        with (
            patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}, clear=True),
            create_adapter(
                mock_registry=mock_registry,
                mock_governance=mock_governance,
            ) as (adapter, client, _, _),
        ):
            result = await adapter.generate_query(
                research_space_description="MED13 project",
                user_instructions="Find MED13 interactions",
                source_type="PUBMED",
                user_id="user-1",
                correlation_id="corr-1",
            )
            assert result.decision == "generated"
            assert result.source_type == "pubmed"
            assert result.query == "MED13[Title/Abstract]"
            assert adapter.get_last_run_id() is not None
            assert adapter.get_last_run_id().startswith("query:pubmed:")
            client.step.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_generate_query_step_error_returns_escalate(
        self,
        mock_registry: MagicMock,
        mock_governance: MagicMock,
    ) -> None:
        with (
            patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}, clear=True),
            create_adapter(
                mock_registry=mock_registry,
                mock_governance=mock_governance,
                step_error=RuntimeError("network timeout"),
            ) as (adapter, _, _, _),
        ):
            result = await adapter.generate_query(
                research_space_description="test",
                user_instructions="test",
                source_type="pubmed",
            )
            assert result.decision == "escalate"
            assert "network timeout" in result.rationale

    @pytest.mark.asyncio
    async def test_close_closes_kernel_and_model_port(
        self,
        mock_registry: MagicMock,
        mock_governance: MagicMock,
    ) -> None:
        with create_adapter(
            mock_registry=mock_registry,
            mock_governance=mock_governance,
        ) as (adapter, _, kernel, model_port):
            await adapter.close()
            kernel.close.assert_awaited_once()
            model_port.aclose.assert_awaited_once()
