"""Tests for embedding provider environment mode resolution."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from src.infrastructure.embeddings.text_embedding_provider import (
    HybridTextEmbeddingProvider,
)
from src.infrastructure.llm.costs import (
    DirectCostUsage,
    activate_cost_usage_recorder,
)


def test_strict_mode_defaults_off_in_testing(monkeypatch) -> None:
    monkeypatch.setenv("TESTING", "true")
    monkeypatch.delenv("MED13_AI_STRICT_MODE", raising=False)
    monkeypatch.delenv("MED13_EMBEDDING_STRICT_MODE", raising=False)

    provider = HybridTextEmbeddingProvider()

    assert provider._strict_ai_mode is False


def test_strict_mode_defaults_on_outside_testing(monkeypatch) -> None:
    monkeypatch.delenv("TESTING", raising=False)
    monkeypatch.delenv("MED13_AI_STRICT_MODE", raising=False)
    monkeypatch.delenv("MED13_EMBEDDING_STRICT_MODE", raising=False)

    provider = HybridTextEmbeddingProvider()

    assert provider._strict_ai_mode is True


def test_primary_strict_env_overrides_legacy_and_testing(monkeypatch) -> None:
    monkeypatch.setenv("TESTING", "true")
    monkeypatch.setenv("MED13_AI_STRICT_MODE", "true")
    monkeypatch.setenv("MED13_EMBEDDING_STRICT_MODE", "false")

    provider = HybridTextEmbeddingProvider()

    assert provider._strict_ai_mode is True


def test_legacy_strict_env_applies_when_primary_missing(monkeypatch) -> None:
    monkeypatch.setenv("TESTING", "false")
    monkeypatch.delenv("MED13_AI_STRICT_MODE", raising=False)
    monkeypatch.setenv("MED13_EMBEDDING_STRICT_MODE", "false")

    provider = HybridTextEmbeddingProvider()

    assert provider._strict_ai_mode is False


def test_embedding_provider_records_openai_embedding_cost() -> None:
    provider = HybridTextEmbeddingProvider()
    registry = MagicMock()
    registry.get_cost_config.return_value = {
        "prompt_tokens_per_1k": 0.00002,
        "completion_tokens_per_1k": 0.0,
    }
    captured: list[DirectCostUsage] = []

    with (
        patch(
            "src.infrastructure.llm.costs.get_model_registry",
            return_value=registry,
        ),
        activate_cost_usage_recorder(captured.append),
    ):
        provider._record_embedding_cost(
            payload={"usage": {"prompt_tokens": 1500}},
            model_name="text-embedding-3-small",
        )

    assert captured == [
        DirectCostUsage(
            provider="openai",
            model_id="text-embedding-3-small",
            operation="embeddings",
            cost_usd=0.00003,
            prompt_tokens=1500,
            completion_tokens=0,
            stage=None,
        ),
    ]
