"""Application-level governance evaluator for extraction agents."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.type_definitions.common import ResearchSpaceSettings


@dataclass(frozen=True)
class GovernancePolicy:
    """Policy settings that drive governance evaluation behavior."""

    confidence_threshold: float = 0.85
    require_evidence: bool = True

    @classmethod
    def from_environment(cls) -> GovernancePolicy:
        """Build governance policy from environment variables."""
        threshold_raw = os.getenv("FLUJO_GOVERNANCE_CONFIDENCE_THRESHOLD", "0.85")
        try:
            threshold = float(threshold_raw)
        except ValueError:
            threshold = 0.85
        normalized_threshold = max(0.0, min(threshold, 1.0))
        require_evidence = os.getenv("FLUJO_GOVERNANCE_REQUIRE_EVIDENCE", "1") == "1"
        return cls(
            confidence_threshold=normalized_threshold,
            require_evidence=require_evidence,
        )


@dataclass(frozen=True)
class GovernanceDecision:
    """Result of governance evaluation for one agent output."""

    allow_write: bool
    requires_review: bool
    shadow_mode: bool
    reason: str


class GovernanceService:
    """Evaluate whether an agent output can persist side effects."""

    def __init__(self, policy: GovernancePolicy | None = None) -> None:
        self._policy = policy or GovernancePolicy.from_environment()

    def evaluate(  # noqa: PLR0911
        self,
        *,
        confidence_score: float,
        evidence_count: int,
        decision: str,
        requested_shadow_mode: bool,
        research_space_settings: ResearchSpaceSettings | None = None,
    ) -> GovernanceDecision:
        if requested_shadow_mode:
            return GovernanceDecision(
                allow_write=False,
                requires_review=False,
                shadow_mode=True,
                reason="shadow_mode_enabled",
            )

        if decision == "escalate":
            return GovernanceDecision(
                allow_write=False,
                requires_review=True,
                shadow_mode=False,
                reason="agent_requested_escalation",
            )

        if self._requires_review_by_space_policy(research_space_settings):
            return GovernanceDecision(
                allow_write=False,
                requires_review=True,
                shadow_mode=False,
                reason="research_space_requires_review",
            )

        threshold = self._resolve_threshold(research_space_settings)
        has_evidence = evidence_count > 0
        if confidence_score < threshold:
            return GovernanceDecision(
                allow_write=False,
                requires_review=True,
                shadow_mode=False,
                reason="confidence_below_threshold",
            )

        if self._policy.require_evidence and not has_evidence:
            return GovernanceDecision(
                allow_write=False,
                requires_review=True,
                shadow_mode=False,
                reason="evidence_required",
            )

        auto_approve = self._resolve_auto_approve(research_space_settings)
        if not auto_approve:
            return GovernanceDecision(
                allow_write=False,
                requires_review=True,
                shadow_mode=False,
                reason="auto_approve_disabled",
            )

        return GovernanceDecision(
            allow_write=True,
            requires_review=False,
            shadow_mode=False,
            reason="approved",
        )

    def _resolve_threshold(self, settings: ResearchSpaceSettings | None) -> float:
        if settings is None:
            return self._policy.confidence_threshold
        threshold = settings.get("review_threshold")
        if isinstance(threshold, float | int):
            return max(0.0, min(float(threshold), 1.0))
        return self._policy.confidence_threshold

    @staticmethod
    def _resolve_auto_approve(settings: ResearchSpaceSettings | None) -> bool:
        if settings is None:
            return True
        auto_approve = settings.get("auto_approve")
        if isinstance(auto_approve, bool):
            return auto_approve
        return True

    @staticmethod
    def _requires_review_by_space_policy(
        settings: ResearchSpaceSettings | None,
    ) -> bool:
        if settings is None:
            return False
        require_review = settings.get("require_review")
        return bool(require_review) if isinstance(require_review, bool) else False


__all__ = ["GovernanceDecision", "GovernancePolicy", "GovernanceService"]
