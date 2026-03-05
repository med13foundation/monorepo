"""Unit tests for deterministic hybrid graph scoring helpers."""

from __future__ import annotations

import pytest

from src.application.services.kernel.hybrid_graph_scoring import (
    compute_jaccard_overlap,
    compute_relation_prior_score,
    compute_relation_suggestion_score,
    compute_similarity_score,
)


def test_compute_jaccard_overlap_returns_expected_ratio() -> None:
    overlap = compute_jaccard_overlap(
        {"a", "b", "c"},
        {"b", "c", "d"},
    )
    assert overlap == pytest.approx(0.5)


def test_compute_similarity_score_blends_vector_and_graph_components() -> None:
    blended = compute_similarity_score(vector_score=0.9, graph_overlap_score=0.5)
    assert blended == pytest.approx(0.82)


def test_relation_prior_score_defaults_to_half_when_sparse() -> None:
    assert compute_relation_prior_score(pair_count=1, total_count=2) == 0.5


def test_relation_prior_score_normalizes_when_sufficient_counts() -> None:
    assert compute_relation_prior_score(pair_count=2, total_count=4) == 0.5
    assert compute_relation_prior_score(pair_count=4, total_count=4) == 1.0


def test_relation_suggestion_score_uses_weighted_formula() -> None:
    score = compute_relation_suggestion_score(
        vector_score=0.8,
        graph_overlap_score=0.5,
        relation_prior_score=0.25,
    )
    assert score == pytest.approx(0.685)
