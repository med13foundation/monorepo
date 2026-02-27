"""Tests for ArtanaModelRegistry model configuration."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from src.domain.agents.models import (
    ModelCapability,
    ModelCostTier,
    ModelReasoningSettings,
    ModelSpec,
)
from src.infrastructure.llm.config.model_registry import (
    ArtanaModelRegistry,
    get_model_registry,
)


class TestModelSpec:
    """Tests for the ModelSpec domain entity."""

    def test_basic_model_spec_creation(self) -> None:
        """Should create a model spec with required fields."""
        spec = ModelSpec(
            model_id="openai:gpt-4o-mini",
            display_name="GPT-4o Mini",
            provider="openai",
            prompt_tokens_per_1k=0.00015,
            completion_tokens_per_1k=0.0006,
        )
        assert spec.model_id == "openai:gpt-4o-mini"
        assert spec.display_name == "GPT-4o Mini"
        assert spec.provider == "openai"
        assert spec.is_reasoning_model is False
        assert spec.is_enabled is True

    def test_reasoning_model_spec_creation(self) -> None:
        """Should create a reasoning model with settings."""
        spec = ModelSpec(
            model_id="openai:gpt-5",
            display_name="GPT-5",
            provider="openai",
            is_reasoning_model=True,
            default_reasoning_settings=ModelReasoningSettings(
                effort="high",
                verbosity="high",
            ),
            prompt_tokens_per_1k=0.00125,
            completion_tokens_per_1k=0.01,
        )
        assert spec.is_reasoning_model is True
        assert spec.default_reasoning_settings is not None
        assert spec.default_reasoning_settings.effort == "high"

    def test_get_reasoning_settings_non_reasoning_model(self) -> None:
        """Non-reasoning models should return None for reasoning settings."""
        spec = ModelSpec(
            model_id="openai:gpt-4o-mini",
            display_name="GPT-4o Mini",
            provider="openai",
            prompt_tokens_per_1k=0.00015,
            completion_tokens_per_1k=0.0006,
        )
        assert spec.get_reasoning_settings() is None

    def test_get_reasoning_settings_reasoning_model(self) -> None:
        """Reasoning models should return OpenAI-compatible settings."""
        spec = ModelSpec(
            model_id="openai:gpt-5",
            display_name="GPT-5",
            provider="openai",
            is_reasoning_model=True,
            default_reasoning_settings=ModelReasoningSettings(
                effort="high",
                verbosity="high",
            ),
            prompt_tokens_per_1k=0.00125,
            completion_tokens_per_1k=0.01,
        )
        settings = spec.get_reasoning_settings()
        assert settings is not None
        assert "reasoning" in settings
        assert settings["reasoning"]["effort"] == "high"
        # Verbosity maps to text.verbosity for OpenAI reasoning models
        assert "text" in settings
        assert settings["text"]["verbosity"] == "high"

    def test_get_reasoning_settings_with_override(self) -> None:
        """Should allow overriding the default effort level."""
        spec = ModelSpec(
            model_id="openai:gpt-5",
            display_name="GPT-5",
            provider="openai",
            is_reasoning_model=True,
            default_reasoning_settings=ModelReasoningSettings(
                effort="high",
                verbosity="high",
            ),
            prompt_tokens_per_1k=0.00125,
            completion_tokens_per_1k=0.01,
        )
        settings = spec.get_reasoning_settings(effort="low")
        assert settings is not None
        assert settings["reasoning"]["effort"] == "low"

    def test_get_reasoning_settings_legacy_summary_compatibility(self) -> None:
        """Legacy summary settings should still map to valid verbosity values."""
        spec = ModelSpec(
            model_id="openai:gpt-5",
            display_name="GPT-5",
            provider="openai",
            is_reasoning_model=True,
            default_reasoning_settings=ModelReasoningSettings(
                effort="medium",
                verbosity=None,
                summary="brief",
            ),
            prompt_tokens_per_1k=0.00125,
            completion_tokens_per_1k=0.01,
        )
        settings = spec.get_reasoning_settings()
        assert settings is not None
        assert settings["text"]["verbosity"] == "low"

    def test_model_capabilities_frozenset(self) -> None:
        """Capabilities should be immutable."""
        spec = ModelSpec(
            model_id="openai:gpt-4o-mini",
            display_name="GPT-4o Mini",
            provider="openai",
            capabilities=frozenset({ModelCapability.QUERY_GENERATION}),
            prompt_tokens_per_1k=0.00015,
            completion_tokens_per_1k=0.0006,
        )
        assert ModelCapability.QUERY_GENERATION in spec.capabilities


class TestArtanaModelRegistry:
    """Tests for the ArtanaModelRegistry infrastructure component."""

    def test_registry_loads_from_artana_toml(self) -> None:
        """Registry should load models from artana.toml."""
        registry = ArtanaModelRegistry()
        models = registry.get_available_models()
        assert len(models) > 0

    def test_get_model_returns_spec(self) -> None:
        """Should return a ModelSpec for valid model ID."""
        registry = ArtanaModelRegistry()
        # gpt-4o-mini should be in default config
        spec = registry.get_model("openai:gpt-4o-mini")
        assert spec.model_id == "openai:gpt-4o-mini"
        assert spec.provider == "openai"

    def test_get_model_raises_for_unknown(self) -> None:
        """Should raise KeyError for unknown model ID."""
        registry = ArtanaModelRegistry()
        with pytest.raises(KeyError):
            registry.get_model("unknown:model-xyz")

    def test_get_models_for_capability(self) -> None:
        """Should filter models by capability."""
        registry = ArtanaModelRegistry()
        query_models = registry.get_models_for_capability(
            ModelCapability.QUERY_GENERATION,
        )
        # All returned models should have the capability
        for model in query_models:
            assert ModelCapability.QUERY_GENERATION in model.capabilities

    def test_get_default_model_for_capability(self) -> None:
        """Should return default model for a capability."""
        registry = ArtanaModelRegistry()
        default = registry.get_default_model(ModelCapability.QUERY_GENERATION)
        assert default is not None
        assert ModelCapability.QUERY_GENERATION in default.capabilities

    def test_validate_model_for_capability_valid(self) -> None:
        """Should return True for valid model/capability combo."""
        registry = ArtanaModelRegistry()
        # gpt-4o-mini should support query generation
        assert registry.validate_model_for_capability(
            "openai:gpt-4o-mini",
            ModelCapability.QUERY_GENERATION,
        )

    def test_validate_model_for_capability_invalid_model(self) -> None:
        """Should return False for unknown model."""
        registry = ArtanaModelRegistry()
        assert not registry.validate_model_for_capability(
            "unknown:model",
            ModelCapability.QUERY_GENERATION,
        )

    def test_list_model_ids(self) -> None:
        """Should return list of all model IDs."""
        registry = ArtanaModelRegistry()
        ids = registry.list_model_ids()
        assert isinstance(ids, list)
        assert len(ids) > 0
        assert all(isinstance(mid, str) for mid in ids)

    def test_env_var_override_for_default(self) -> None:
        """Environment variable should override artana.toml default."""
        # The env var pattern is MED13_AI_{CAPABILITY}_MODEL
        env_model = "openai:gpt-5"
        with patch.dict(
            os.environ,
            {"MED13_AI_QUERY_GENERATION_MODEL": env_model},
        ):
            registry = ArtanaModelRegistry()
            # Check if gpt-5 is configured and supports query_generation
            supports = registry.validate_model_for_capability(
                env_model,
                ModelCapability.QUERY_GENERATION,
            )
            default = registry.get_default_model(ModelCapability.QUERY_GENERATION)

            if supports:
                assert default.model_id == env_model
            else:
                # If model doesn't support capability, should fall back
                # Just ensure we get a valid model
                assert default is not None
                assert ModelCapability.QUERY_GENERATION in default.capabilities


class TestGetModelRegistry:
    """Tests for the singleton registry accessor."""

    def test_returns_same_instance(self) -> None:
        """Should return the same registry instance (singleton)."""
        registry1 = get_model_registry()
        registry2 = get_model_registry()
        assert registry1 is registry2

    def test_instance_is_artana_registry(self) -> None:
        """Should return an ArtanaModelRegistry instance."""
        registry = get_model_registry()
        assert isinstance(registry, ArtanaModelRegistry)


class TestModelCostTier:
    """Tests for the ModelCostTier enum."""

    def test_cost_tiers_exist(self) -> None:
        """Should have expected cost tiers."""
        assert ModelCostTier.LOW.value == "low"
        assert ModelCostTier.MEDIUM.value == "medium"
        assert ModelCostTier.HIGH.value == "high"


class TestModelCapability:
    """Tests for the ModelCapability enum."""

    def test_capabilities_exist(self) -> None:
        """Should have expected capabilities."""
        assert ModelCapability.QUERY_GENERATION.value == "query_generation"
        assert ModelCapability.EVIDENCE_EXTRACTION.value == "evidence_extraction"
        assert ModelCapability.CURATION.value == "curation"
        assert ModelCapability.JUDGE.value == "judge"
