"""Tests for FlujoQueryAgentAdapter model selection functionality."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.domain.agents.models import ModelCapability, ModelSpec
from src.infrastructure.llm.adapters.query_agent_adapter import FlujoQueryAgentAdapter
from src.infrastructure.llm.config import QuerySourcePolicy, UsageLimits


class TestFlujoQueryAgentAdapterModelSelection:
    """Tests for model selection in the query agent adapter."""

    @pytest.fixture
    def mock_registry(self) -> MagicMock:
        """Create a mock model registry."""
        registry = MagicMock()

        # Create mock model specs
        gpt4o_mini = ModelSpec(
            model_id="openai:gpt-4o-mini",
            display_name="GPT-4o Mini",
            provider="openai",
            capabilities=frozenset({ModelCapability.QUERY_GENERATION}),
            prompt_tokens_per_1k=0.00015,
            completion_tokens_per_1k=0.0006,
            is_default=True,
        )
        gpt5 = ModelSpec(
            model_id="openai:gpt-5",
            display_name="GPT-5",
            provider="openai",
            capabilities=frozenset(
                {
                    ModelCapability.QUERY_GENERATION,
                    ModelCapability.EVIDENCE_EXTRACTION,
                },
            ),
            is_reasoning_model=True,
            prompt_tokens_per_1k=0.00125,
            completion_tokens_per_1k=0.01,
        )

        registry.get_default_model.return_value = gpt4o_mini
        registry.get_model.side_effect = lambda mid: {
            "openai:gpt-4o-mini": gpt4o_mini,
            "openai:gpt-5": gpt5,
        }.get(mid, KeyError(mid))
        registry.validate_model_for_capability.return_value = True

        return registry

    @pytest.fixture
    def mock_pipeline(self) -> MagicMock:
        """Create a mock Flujo pipeline that returns escalate contract."""
        pipeline = MagicMock()

        # Return an empty async iterator - the adapter will return
        # empty_result_contract for this case
        async def mock_run_async(
            *args: object,
            **kwargs: object,
        ) -> object:  # type: ignore[misc]
            # Return nothing - pipeline produces no output
            return
            yield  # Make this a generator

        pipeline.run_async = mock_run_async
        return pipeline

    def test_adapter_initializes_with_default_model(
        self,
        mock_registry: MagicMock,
    ) -> None:
        """Adapter should initialize with the default model from registry."""
        with (
            patch(
                "src.infrastructure.llm.adapters.query_agent_adapter.get_model_registry",
                return_value=mock_registry,
            ),
            patch(
                "src.infrastructure.llm.adapters.query_agent_adapter.get_state_backend",
            ),
            patch(
                "src.infrastructure.llm.adapters.query_agent_adapter.get_lifecycle_manager",
            ),
            patch(
                "src.infrastructure.llm.adapters.query_agent_adapter.create_pubmed_query_pipeline",
            ),
        ):
            adapter = FlujoQueryAgentAdapter()
            assert adapter._registry is mock_registry

    def test_resolve_model_id_with_none_returns_default(
        self,
        mock_registry: MagicMock,
    ) -> None:
        """When model_id is None, should resolve to default."""
        with (
            patch(
                "src.infrastructure.llm.adapters.query_agent_adapter.get_model_registry",
                return_value=mock_registry,
            ),
            patch(
                "src.infrastructure.llm.adapters.query_agent_adapter.get_state_backend",
            ),
            patch(
                "src.infrastructure.llm.adapters.query_agent_adapter.get_lifecycle_manager",
            ),
            patch(
                "src.infrastructure.llm.adapters.query_agent_adapter.create_pubmed_query_pipeline",
            ),
        ):
            adapter = FlujoQueryAgentAdapter()
            resolved = adapter._resolve_model_id("pubmed")
            assert resolved == "openai:gpt-4o-mini"

    def test_resolve_model_id_with_valid_model(
        self,
        mock_registry: MagicMock,
    ) -> None:
        """When valid model_id is provided, should return it."""
        with (
            patch(
                "src.infrastructure.llm.adapters.query_agent_adapter.get_model_registry",
                return_value=mock_registry,
            ),
            patch(
                "src.infrastructure.llm.adapters.query_agent_adapter.get_state_backend",
            ),
            patch(
                "src.infrastructure.llm.adapters.query_agent_adapter.get_lifecycle_manager",
            ),
            patch(
                "src.infrastructure.llm.adapters.query_agent_adapter.create_pubmed_query_pipeline",
            ),
        ):
            adapter = FlujoQueryAgentAdapter()
            resolved = adapter._resolve_model_id("pubmed", "openai:gpt-5")
            assert resolved == "openai:gpt-5"

    def test_resolve_model_id_with_invalid_model_falls_back(
        self,
        mock_registry: MagicMock,
    ) -> None:
        """When invalid model_id is provided, should fall back to default."""
        mock_registry.validate_model_for_capability.return_value = False
        with (
            patch(
                "src.infrastructure.llm.adapters.query_agent_adapter.get_model_registry",
                return_value=mock_registry,
            ),
            patch(
                "src.infrastructure.llm.adapters.query_agent_adapter.get_state_backend",
            ),
            patch(
                "src.infrastructure.llm.adapters.query_agent_adapter.get_lifecycle_manager",
            ),
            patch(
                "src.infrastructure.llm.adapters.query_agent_adapter.create_pubmed_query_pipeline",
            ),
        ):
            adapter = FlujoQueryAgentAdapter()
            resolved = adapter._resolve_model_id("pubmed", "invalid:model")
            # Should fall back to default
            assert resolved == "openai:gpt-4o-mini"

    def test_is_supported_source_pubmed(
        self,
        mock_registry: MagicMock,
    ) -> None:
        """Should support pubmed source type."""
        with (
            patch(
                "src.infrastructure.llm.adapters.query_agent_adapter.get_model_registry",
                return_value=mock_registry,
            ),
            patch(
                "src.infrastructure.llm.adapters.query_agent_adapter.get_state_backend",
            ),
            patch(
                "src.infrastructure.llm.adapters.query_agent_adapter.get_lifecycle_manager",
            ),
            patch(
                "src.infrastructure.llm.adapters.query_agent_adapter.create_pubmed_query_pipeline",
            ),
        ):
            adapter = FlujoQueryAgentAdapter()
            assert adapter._is_supported_source("pubmed")
            assert adapter._is_supported_source("PUBMED")
            assert adapter._is_supported_source("clinvar")

    def test_resolve_model_id_with_source_override(
        self,
        mock_registry: MagicMock,
    ) -> None:
        """Should resolve source-level model override before default."""
        policies = {
            "clinvar": QuerySourcePolicy(
                model_id="openai:gpt-5",
            ),
        }

        with (
            patch(
                "src.infrastructure.llm.adapters.query_agent_adapter.get_model_registry",
                return_value=mock_registry,
            ),
            patch(
                "src.infrastructure.llm.adapters.query_agent_adapter.get_state_backend",
            ),
            patch(
                "src.infrastructure.llm.adapters.query_agent_adapter.get_lifecycle_manager",
            ),
            patch(
                "src.infrastructure.llm.adapters.query_agent_adapter.create_pubmed_query_pipeline",
            ),
            patch(
                "src.infrastructure.llm.adapters.query_agent_adapter.load_query_source_policies",
                return_value=policies,
            ),
        ):
            adapter = FlujoQueryAgentAdapter()
            resolved = adapter._resolve_model_id("clinvar")
            assert resolved == "openai:gpt-5"

    def test_resolve_usage_limits_from_source_profile(
        self,
        mock_registry: MagicMock,
    ) -> None:
        """Should resolve source-specific limits with governance fallback."""
        policies = {
            "clinvar": QuerySourcePolicy(
                model_id=None,
                usage_limits=UsageLimits(
                    total_cost_usd=2.5,
                    max_turns=None,
                    max_tokens=2048,
                ),
            ),
        }

        with (
            patch(
                "src.infrastructure.llm.adapters.query_agent_adapter.get_model_registry",
                return_value=mock_registry,
            ),
            patch(
                "src.infrastructure.llm.adapters.query_agent_adapter.get_state_backend",
            ),
            patch(
                "src.infrastructure.llm.adapters.query_agent_adapter.get_lifecycle_manager",
            ),
            patch(
                "src.infrastructure.llm.adapters.query_agent_adapter.create_pubmed_query_pipeline",
            ),
            patch(
                "src.infrastructure.llm.adapters.query_agent_adapter.load_query_source_policies",
                return_value=policies,
            ),
            patch(
                "src.infrastructure.llm.adapters.query_agent_adapter.GovernanceConfig.from_environment",
                return_value=MagicMock(
                    usage_limits=MagicMock(
                        total_cost_usd=1.0,
                        max_turns=10,
                        max_tokens=8192,
                    ),
                ),
            ),
        ):
            adapter = FlujoQueryAgentAdapter()
            limits = adapter._resolve_usage_limits("clinvar")
            assert limits.total_cost_usd == 2.5
            assert limits.max_turns == 10
            assert limits.max_tokens == 2048

    def test_is_openai_model_detection(
        self,
        mock_registry: MagicMock,
    ) -> None:
        """Should correctly detect OpenAI models."""
        with (
            patch(
                "src.infrastructure.llm.adapters.query_agent_adapter.get_model_registry",
                return_value=mock_registry,
            ),
            patch(
                "src.infrastructure.llm.adapters.query_agent_adapter.get_state_backend",
            ),
            patch(
                "src.infrastructure.llm.adapters.query_agent_adapter.get_lifecycle_manager",
            ),
            patch(
                "src.infrastructure.llm.adapters.query_agent_adapter.create_pubmed_query_pipeline",
            ),
        ):
            adapter = FlujoQueryAgentAdapter()
            assert adapter._is_openai_model("openai:gpt-4o-mini")
            assert adapter._is_openai_model("openai:gpt-5")
            assert not adapter._is_openai_model("anthropic:claude-3")

    def test_pipeline_caching_creates_for_different_models(
        self,
        mock_registry: MagicMock,
        mock_pipeline: MagicMock,
    ) -> None:
        """Should create separate pipelines for different models."""
        create_pipeline_mock = MagicMock(return_value=mock_pipeline)

        with (
            patch(
                "src.infrastructure.llm.adapters.query_agent_adapter.get_model_registry",
                return_value=mock_registry,
            ),
            patch(
                "src.infrastructure.llm.adapters.query_agent_adapter.get_state_backend",
            ),
            patch(
                "src.infrastructure.llm.adapters.query_agent_adapter.get_lifecycle_manager",
            ),
            patch(
                "src.infrastructure.llm.adapters.query_agent_adapter.create_pubmed_query_pipeline",
                create_pipeline_mock,
            ),
        ):
            adapter = FlujoQueryAgentAdapter()

            # Get pipeline for first model (created during init)
            adapter._get_or_create_pipeline("pubmed", "openai:gpt-4o-mini")

            # Get pipeline for second model
            adapter._get_or_create_pipeline("pubmed", "openai:gpt-5")

            # Should have two pipelines in cache
            assert ("pubmed", "openai:gpt-4o-mini") in adapter._pipelines
            assert ("pubmed", "openai:gpt-5") in adapter._pipelines

    def test_pipeline_caching_reuses_same_model(
        self,
        mock_registry: MagicMock,
        mock_pipeline: MagicMock,
    ) -> None:
        """Should reuse cached pipeline for same model."""
        create_pipeline_mock = MagicMock(return_value=mock_pipeline)

        with (
            patch(
                "src.infrastructure.llm.adapters.query_agent_adapter.get_model_registry",
                return_value=mock_registry,
            ),
            patch(
                "src.infrastructure.llm.adapters.query_agent_adapter.get_state_backend",
            ),
            patch(
                "src.infrastructure.llm.adapters.query_agent_adapter.get_lifecycle_manager",
            ),
            patch(
                "src.infrastructure.llm.adapters.query_agent_adapter.create_pubmed_query_pipeline",
                create_pipeline_mock,
            ),
        ):
            adapter = FlujoQueryAgentAdapter()
            initial_call_count = create_pipeline_mock.call_count

            # Get pipeline twice for same model
            pipeline1 = adapter._get_or_create_pipeline("pubmed", "openai:gpt-4o-mini")
            pipeline2 = adapter._get_or_create_pipeline("pubmed", "openai:gpt-4o-mini")

            # Should be the same cached instance
            assert pipeline1 is pipeline2
            # Should not have created additional pipeline
            assert create_pipeline_mock.call_count == initial_call_count

    @pytest.mark.asyncio
    async def test_generate_query_uses_clinvar_pipeline(
        self,
        mock_registry: MagicMock,
        mock_pipeline: MagicMock,
    ) -> None:
        """Should route clinvar source to the ClinVar pipeline."""
        mock_state_backend = MagicMock()
        mock_state_backend.load_state = AsyncMock(return_value=None)
        mock_state_backend.save_run_start = AsyncMock(return_value=None)
        mock_state_backend.save_workflow_state = AsyncMock(return_value=None)

        policies = {
            "clinvar": QuerySourcePolicy(
                model_id="openai:gpt-5",
                usage_limits=UsageLimits(
                    total_cost_usd=2.5,
                    max_turns=10,
                    max_tokens=2048,
                ),
            ),
        }
        create_clinvar_pipeline_mock = MagicMock(return_value=mock_pipeline)
        create_pubmed_pipeline_mock = MagicMock(return_value=mock_pipeline)

        with (
            patch(
                "src.infrastructure.llm.adapters.query_agent_adapter.get_model_registry",
                return_value=mock_registry,
            ),
            patch(
                "src.infrastructure.llm.adapters.query_agent_adapter.get_state_backend",
                return_value=mock_state_backend,
            ),
            patch(
                "src.infrastructure.llm.adapters.query_agent_adapter.get_lifecycle_manager",
            ),
            patch.dict(
                "src.infrastructure.llm.adapters.query_agent_adapter._QUERY_PIPELINE_FACTORIES",
                {
                    "pubmed": create_pubmed_pipeline_mock,
                    "clinvar": create_clinvar_pipeline_mock,
                },
            ),
            patch(
                "src.infrastructure.llm.adapters.query_agent_adapter.load_query_source_policies",
                return_value=policies,
            ),
            patch.dict("os.environ", {"OPENAI_API_KEY": "test-openai-key"}),
        ):
            adapter = FlujoQueryAgentAdapter()
            result = await adapter.generate_query(
                research_space_description="Test",
                user_instructions="Test",
                source_type="clinvar",
            )

            assert result.source_type == "clinvar"
            create_clinvar_pipeline_mock.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_query_unsupported_source(
        self,
        mock_registry: MagicMock,
    ) -> None:
        """Should return escalate contract for unsupported source."""
        with (
            patch(
                "src.infrastructure.llm.adapters.query_agent_adapter.get_model_registry",
                return_value=mock_registry,
            ),
            patch(
                "src.infrastructure.llm.adapters.query_agent_adapter.get_state_backend",
            ),
            patch(
                "src.infrastructure.llm.adapters.query_agent_adapter.get_lifecycle_manager",
            ),
            patch(
                "src.infrastructure.llm.adapters.query_agent_adapter.create_pubmed_query_pipeline",
            ),
        ):
            adapter = FlujoQueryAgentAdapter()
            result = await adapter.generate_query(
                research_space_description="Test",
                user_instructions="Test",
                source_type="unsupported_source",
            )

            assert result.decision == "escalate"
            assert "not yet supported" in result.rationale

    @pytest.mark.asyncio
    async def test_generate_query_no_api_key(
        self,
        mock_registry: MagicMock,
    ) -> None:
        """Should return fallback contract when OpenAI key is missing."""
        with (
            patch(
                "src.infrastructure.llm.adapters.query_agent_adapter.get_model_registry",
                return_value=mock_registry,
            ),
            patch(
                "src.infrastructure.llm.adapters.query_agent_adapter.get_state_backend",
            ),
            patch(
                "src.infrastructure.llm.adapters.query_agent_adapter.get_lifecycle_manager",
            ),
            patch(
                "src.infrastructure.llm.adapters.query_agent_adapter.create_pubmed_query_pipeline",
            ),
            patch.dict("os.environ", {}, clear=True),
        ):
            adapter = FlujoQueryAgentAdapter()
            result = await adapter.generate_query(
                research_space_description="Test",
                user_instructions="Test",
                source_type="pubmed",
            )

            assert result.decision == "fallback"
            assert "API key not configured" in result.rationale

    @pytest.mark.asyncio
    async def test_close_cleans_up_all_pipelines(
        self,
        mock_registry: MagicMock,
        mock_pipeline: MagicMock,
    ) -> None:
        """Should close all cached pipelines on close()."""
        mock_pipeline.aclose = AsyncMock()
        lifecycle_manager = MagicMock()

        with (
            patch(
                "src.infrastructure.llm.adapters.query_agent_adapter.get_model_registry",
                return_value=mock_registry,
            ),
            patch(
                "src.infrastructure.llm.adapters.query_agent_adapter.get_state_backend",
            ),
            patch(
                "src.infrastructure.llm.adapters.query_agent_adapter.get_lifecycle_manager",
                return_value=lifecycle_manager,
            ),
            patch(
                "src.infrastructure.llm.adapters.query_agent_adapter.create_pubmed_query_pipeline",
                return_value=mock_pipeline,
            ),
        ):
            adapter = FlujoQueryAgentAdapter()

            # Create a second pipeline for different model
            adapter._get_or_create_pipeline("pubmed", "openai:gpt-5")

            # Should have 2 pipelines
            assert len(adapter._pipelines) == 2

            # Close adapter
            await adapter.close()

            # All pipelines should be cleared
            assert len(adapter._pipelines) == 0
            lifecycle_manager.unregister_runner.assert_called()
