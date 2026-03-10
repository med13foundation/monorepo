"""Tests for source-specific query profile configuration."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

from src.infrastructure.llm.config.governance import UsageLimits
from src.infrastructure.llm.config.query_profiles import (
    QuerySourcePolicy,
    load_query_source_policies,
    resolve_source_policy,
)


def _write_toml(path: Path, content: str) -> None:
    """Write a TOML document to disk."""
    path.write_text(content, encoding="utf-8")


def test_load_query_source_policies_with_inline_limits(
    tmp_path: Path,
) -> None:
    """Should parse inline usage limits and model override."""
    config = tmp_path / "artana.toml"
    _write_toml(
        config,
        """
        [source_profiles]
        [source_profiles.clinvar]
        model = "openai:gpt-5"
        timeout_seconds = 45.0

        [source_profiles.clinvar.usage_limits]
        total_cost_usd = 2.5
        max_turns = 20
        max_tokens = 4096
        """,
    )

    policies = load_query_source_policies(str(config))
    assert "clinvar" in policies

    policy = policies["clinvar"]
    assert isinstance(policy, QuerySourcePolicy)
    assert policy.model_id == "openai:gpt-5"
    assert policy.timeout_seconds == 45.0
    assert policy.usage_limits == UsageLimits(
        total_cost_usd=2.5,
        max_turns=20,
        max_tokens=4096,
    )


def test_load_query_source_policies_from_budget_profile(
    tmp_path: Path,
) -> None:
    """Should resolve usage limits from budget_profile alias."""
    config = tmp_path / "artana.toml"
    _write_toml(
        config,
        """
        [budgets]
        [budgets.research]
        total_cost_usd = 5.0
        max_turns = 25
        max_tokens = 16384

        [source_profiles]
        [source_profiles.pubmed]
        budget_profile = "research"
        timeout_seconds = 30
        """,
    )

    policy = resolve_source_policy("pubmed", str(config))
    assert policy is not None
    assert policy.model_id is None
    assert policy.timeout_seconds == 30.0
    assert policy.usage_limits == UsageLimits(
        total_cost_usd=5.0,
        max_turns=25,
        max_tokens=16384,
    )
