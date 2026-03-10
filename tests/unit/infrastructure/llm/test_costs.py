"""Tests for shared LLM usage cost calculation helpers."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from src.infrastructure.llm.costs import (
    DirectCostUsage,
    activate_cost_usage_recorder,
    calculate_openai_usage_cost_usd,
    normalize_openai_model_id,
    record_cost_usage,
)


def test_normalize_openai_model_id_adds_provider_prefix() -> None:
    assert normalize_openai_model_id("gpt-5-mini") == "openai:gpt-5-mini"
    assert normalize_openai_model_id("openai:gpt-5-mini") == "openai:gpt-5-mini"


def test_calculate_openai_usage_cost_uses_registry_rates() -> None:
    registry = MagicMock()
    registry.get_cost_config.return_value = {
        "prompt_tokens_per_1k": 0.00025,
        "completion_tokens_per_1k": 0.002,
    }

    with patch(
        "src.infrastructure.llm.costs.get_model_registry",
        return_value=registry,
    ):
        cost_usd = calculate_openai_usage_cost_usd(
            model_id="gpt-5-mini",
            prompt_tokens=2000,
            completion_tokens=500,
        )

    assert cost_usd == 0.0015
    registry.get_cost_config.assert_called_once_with("openai:gpt-5-mini")


def test_calculate_openai_usage_cost_clamps_negative_tokens() -> None:
    registry = MagicMock()
    registry.get_cost_config.return_value = {
        "prompt_tokens_per_1k": 0.001,
        "completion_tokens_per_1k": 0.01,
    }

    with patch(
        "src.infrastructure.llm.costs.get_model_registry",
        return_value=registry,
    ):
        cost_usd = calculate_openai_usage_cost_usd(
            model_id="openai:gpt-5",
            prompt_tokens=-10,
            completion_tokens=250,
        )

    assert cost_usd == 0.0025


def test_record_cost_usage_emits_to_active_recorder() -> None:
    captured: list[DirectCostUsage] = []

    with activate_cost_usage_recorder(captured.append):
        record_cost_usage(
            provider="openai",
            model_id="openai:gpt-5-mini",
            operation="chat_completion",
            cost_usd=0.123456789,
            prompt_tokens=1200,
            completion_tokens=300,
            stage="extraction",
        )

    assert captured == [
        DirectCostUsage(
            provider="openai",
            model_id="openai:gpt-5-mini",
            operation="chat_completion",
            cost_usd=0.12345679,
            prompt_tokens=1200,
            completion_tokens=300,
            stage="extraction",
        ),
    ]
