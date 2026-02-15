"""Tests for application-layer governance decisioning."""

from __future__ import annotations

from src.application.agents.services.governance_service import (
    GovernancePolicy,
    GovernanceService,
)


def _build_governance_service() -> GovernanceService:
    policy = GovernancePolicy(
        confidence_threshold=0.8,
        require_evidence=True,
    )
    return GovernanceService(policy=policy)


def test_governance_shadow_mode_short_circuit() -> None:
    service = _build_governance_service()

    decision = service.evaluate(
        confidence_score=1.0,
        evidence_count=5,
        decision="generated",
        requested_shadow_mode=True,
        research_space_settings=None,
    )

    assert decision.shadow_mode is True
    assert decision.allow_write is False
    assert decision.requires_review is False
    assert decision.reason == "shadow_mode_enabled"


def test_governance_rejects_low_confidence() -> None:
    service = _build_governance_service()

    decision = service.evaluate(
        confidence_score=0.4,
        evidence_count=2,
        decision="generated",
        requested_shadow_mode=False,
        research_space_settings=None,
    )

    assert decision.allow_write is True
    assert decision.requires_review is True
    assert decision.reason == "confidence_below_threshold"


def test_governance_requires_evidence_when_configured() -> None:
    service = _build_governance_service()

    decision = service.evaluate(
        confidence_score=0.95,
        evidence_count=0,
        decision="generated",
        requested_shadow_mode=False,
        research_space_settings=None,
    )

    assert decision.allow_write is False
    assert decision.requires_review is True
    assert decision.reason == "evidence_required"


def test_governance_respects_space_auto_approve_toggle() -> None:
    service = _build_governance_service()

    decision = service.evaluate(
        confidence_score=0.95,
        evidence_count=2,
        decision="generated",
        requested_shadow_mode=False,
        research_space_settings={"auto_approve": False},
    )

    assert decision.allow_write is True
    assert decision.requires_review is True
    assert decision.reason == "auto_approve_disabled"


def test_governance_allows_write_when_policy_passes() -> None:
    service = _build_governance_service()

    decision = service.evaluate(
        confidence_score=0.95,
        evidence_count=2,
        decision="generated",
        requested_shadow_mode=False,
        research_space_settings={"auto_approve": True},
    )

    assert decision.allow_write is True
    assert decision.requires_review is False
    assert decision.shadow_mode is False
    assert decision.reason == "approved"


def test_governance_uses_relation_type_threshold_override() -> None:
    service = _build_governance_service()

    decision = service.evaluate(
        confidence_score=0.9,
        evidence_count=2,
        decision="generated",
        requested_shadow_mode=False,
        research_space_settings={
            "review_threshold": 0.6,
            "relation_review_thresholds": {"CAUSES": 0.95},
        },
        relation_types=("CAUSES",),
    )

    assert decision.allow_write is True
    assert decision.requires_review is True
    assert decision.reason == "confidence_below_threshold"


def test_governance_uses_strictest_threshold_for_mixed_relation_types() -> None:
    service = _build_governance_service()

    decision = service.evaluate(
        confidence_score=0.88,
        evidence_count=2,
        decision="generated",
        requested_shadow_mode=False,
        research_space_settings={
            "review_threshold": 0.6,
            "relation_review_thresholds": {
                "ASSOCIATED_WITH": 0.7,
                "CAUSES": 0.9,
            },
        },
        relation_types=("ASSOCIATED_WITH", "CAUSES"),
    )

    assert decision.allow_write is True
    assert decision.requires_review is True
    assert decision.reason == "confidence_below_threshold"


def test_governance_uses_relation_default_threshold_for_unspecified_relation() -> None:
    service = _build_governance_service()

    decision = service.evaluate(
        confidence_score=0.88,
        evidence_count=2,
        decision="generated",
        requested_shadow_mode=False,
        research_space_settings={
            "review_threshold": 0.6,
            "relation_default_review_threshold": 0.9,
            "relation_review_thresholds": {"ASSOCIATED_WITH": 0.7},
        },
        relation_types=("ENHANCES",),
    )

    assert decision.allow_write is True
    assert decision.requires_review is True
    assert decision.reason == "confidence_below_threshold"


def test_governance_supports_legacy_wildcard_default_threshold() -> None:
    service = _build_governance_service()

    decision = service.evaluate(
        confidence_score=0.9,
        evidence_count=2,
        decision="generated",
        requested_shadow_mode=False,
        research_space_settings={
            "review_threshold": 0.6,
            "relation_review_thresholds": {"*": 0.92},
        },
        relation_types=("ENHANCES",),
    )

    assert decision.allow_write is True
    assert decision.requires_review is True
    assert decision.reason == "confidence_below_threshold"
