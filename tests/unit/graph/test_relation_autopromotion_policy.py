"""Unit tests for graph-core relation auto-promotion policy resolution."""

from __future__ import annotations

import pytest

from src.graph.core.relation_autopromotion_policy import AutoPromotionPolicy
from src.graph.domain_biomedical.relation_autopromotion import (
    BIOMEDICAL_RELATION_AUTOPROMOTION_DEFAULTS,
)


def test_autopromotion_policy_prefers_neutral_graph_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GRAPH_RELATION_AUTOPROMOTE_ENABLED", "0")
    monkeypatch.setenv("MED13_RELATION_AUTOPROMOTE_ENABLED", "1")
    monkeypatch.setenv("GRAPH_RELATION_AUTOPROMOTE_MIN_DISTINCT_SOURCES", "7")
    monkeypatch.setenv("MED13_RELATION_AUTOPROMOTE_MIN_DISTINCT_SOURCES", "3")

    policy = AutoPromotionPolicy.from_environment(
        defaults=BIOMEDICAL_RELATION_AUTOPROMOTION_DEFAULTS,
    )

    assert policy.enabled is False
    assert policy.min_distinct_sources == 7


def test_autopromotion_policy_ignores_legacy_med13_aliases(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GRAPH_RELATION_AUTOPROMOTE_ENABLED", raising=False)
    monkeypatch.delenv("GRAPH_RELATION_AUTOPROMOTE_MIN_EVIDENCE_TIER", raising=False)
    monkeypatch.setenv("MED13_RELATION_AUTOPROMOTE_ENABLED", "0")
    monkeypatch.setenv("MED13_RELATION_AUTOPROMOTE_MIN_EVIDENCE_TIER", "clinical")

    policy = AutoPromotionPolicy.from_environment(
        defaults=BIOMEDICAL_RELATION_AUTOPROMOTION_DEFAULTS,
    )

    assert policy.enabled is BIOMEDICAL_RELATION_AUTOPROMOTION_DEFAULTS.enabled
    assert (
        policy.min_evidence_tier
        == BIOMEDICAL_RELATION_AUTOPROMOTION_DEFAULTS.min_evidence_tier
    )
