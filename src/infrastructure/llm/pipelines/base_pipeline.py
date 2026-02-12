"""
Base pipeline patterns for AI agents.

Provides common governance patterns including confidence-based
routing, human-in-the-loop escalation, and usage limits.

Type Safety Note:
    This module uses `Any` types for Flujo library generic parameters.
    This is a documented exception to the project's strict "Never Any" policy.

    Rationale:
    - Flujo's Step.granular() returns Pipeline[Any, Any] instead of Step
    - Flujo's generic type parameters are not fully compatible with strict typing
    - The Any usage is confined to infrastructure layer only
    - Domain contracts (QueryGenerationContract, etc.) remain fully typed

    The type ignores are:
    - Step.granular() returns Pipeline, not Step (type: ignore[arg-type])
    - Generic parameter constraints in Flujo DSL types
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from flujo import Pipeline, Step
from flujo.domain.dsl import ConditionalStep, GranularStep, HumanInTheLoopStep

from src.infrastructure.llm.config.governance import GovernanceConfig, UsageLimits

if TYPE_CHECKING:
    from collections.abc import Callable

logger = logging.getLogger(__name__)


def check_confidence(
    output: object,
    _ctx: object,
    threshold: float = 0.85,
    *,
    require_evidence: bool = True,
) -> str:
    """
    Check if output confidence meets the threshold for auto-approval.

    Args:
        output: Agent output with confidence_score
        _ctx: Pipeline context (unused)
        threshold: Minimum confidence for auto-approval
        require_evidence: Whether evidence is required for approval

    Returns:
        "proceed" if confidence is sufficient, "escalate" otherwise
    """
    if not hasattr(output, "confidence_score"):
        return "escalate"

    confidence = getattr(output, "confidence_score", 0.0)

    # Check evidence requirement
    if require_evidence:
        evidence = getattr(output, "evidence", [])
        if not evidence:
            logger.debug("Escalating: no evidence provided")
            return "escalate"

    return "proceed" if confidence >= threshold else "escalate"


def create_confidence_checker(
    threshold: float,
    *,
    require_evidence: bool = True,
) -> Callable[[object, object], str]:
    """
    Create a confidence checker with a specific threshold.

    Args:
        threshold: Minimum confidence for auto-approval
        require_evidence: Whether evidence is required

    Returns:
        Callable for use with ConditionalStep
    """

    def _check(output: object, ctx: object) -> str:
        return check_confidence(
            output,
            ctx,
            threshold,
            require_evidence=require_evidence,
        )

    return _check


def create_governance_gate(
    name: str,
    governance_config: GovernanceConfig | None = None,
    escalation_message: str = "Low confidence decision. Review required.",
) -> ConditionalStep[Any]:
    """
    Create a standard governance gate for confidence-based routing.

    Args:
        name: Name for the governance step
        governance_config: Optional governance configuration
        escalation_message: Message shown when escalating to human review

    Returns:
        ConditionalStep configured for confidence-based routing
    """
    config = governance_config or GovernanceConfig.from_environment()

    return ConditionalStep(
        name=name,
        condition_callable=create_confidence_checker(
            config.confidence_threshold,
            require_evidence=config.require_evidence,
        ),
        branches={
            "escalate": Pipeline(
                steps=[
                    HumanInTheLoopStep(
                        name=f"{name}_human_review",
                        message_for_user=escalation_message,
                    ),
                ],
            ),
            "proceed": Pipeline(steps=[]),
        },
    )


def get_usage_limits_dict(limits: UsageLimits | None = None) -> dict[str, float | int]:
    """
    Convert UsageLimits to a dict for Flujo runner configuration.

    Args:
        limits: Usage limits configuration

    Returns:
        Dict suitable for Flujo UsageLimits initialization
    """
    if limits is None:
        limits = UsageLimits.from_environment()

    result: dict[str, float | int] = {}
    if limits.total_cost_usd is not None:
        result["total_cost_usd_limit"] = limits.total_cost_usd
    if limits.max_turns is not None:
        logger.debug(
            "max_turns is tracked by Flujo governance layer; Flujo usage_limits "
            "uses total_tokens_limit, not turns.",
        )
    if limits.max_tokens is not None:
        result["total_tokens_limit"] = limits.max_tokens
    return result


class PipelineBuilder:
    """
    Builder for creating pipelines with standard governance patterns.

    Provides a fluent interface for constructing pipelines with
    consistent governance, durability, and usage limit settings.
    """

    def __init__(
        self,
        name: str,
        governance_config: GovernanceConfig | None = None,
    ) -> None:
        """
        Initialize the pipeline builder.

        Args:
            name: Name for the pipeline
            governance_config: Optional governance configuration
        """
        self._name = name
        self._governance = governance_config or GovernanceConfig.from_environment()
        self._steps: list[Step[Any, Any] | GranularStep | ConditionalStep[Any]] = []
        self._use_granular: bool = True
        self._enforce_idempotency: bool = True
        self._usage_limits: UsageLimits | None = None

    def with_agent_step(
        self,
        step_name: str,
        agent: object,
        *,
        granular: bool = True,
        idempotent: bool = True,
    ) -> PipelineBuilder:
        """
        Add an agent step to the pipeline.

        Args:
            step_name: Name for the step
            agent: The agent to execute
            granular: Use granular durability
            idempotent: Enforce idempotency

        Returns:
            Self for chaining
        """
        if granular:
            # Use GranularStep directly for per-turn durability
            self._steps.append(
                GranularStep(
                    name=step_name,
                    agent=agent,
                    enforce_idempotency=idempotent,
                    history_max_tokens=8192,
                ),
            )
        else:
            self._steps.append(
                Step(
                    name=step_name,
                    agent=agent,
                ),
            )
        return self

    def with_governance_gate(
        self,
        escalation_message: str = "Low confidence. Review required.",
    ) -> PipelineBuilder:
        """
        Add a governance gate for confidence-based routing.

        Args:
            escalation_message: Message for human review

        Returns:
            Self for chaining
        """
        gate = create_governance_gate(
            name=f"{self._name}_governance",
            governance_config=self._governance,
            escalation_message=escalation_message,
        )
        self._steps.append(gate)
        return self

    def with_usage_limits(
        self,
        limits: UsageLimits | None = None,
    ) -> PipelineBuilder:
        """
        Set usage limits for the pipeline.

        Args:
            limits: Usage limits configuration (defaults to environment)

        Returns:
            Self for chaining
        """
        self._usage_limits = limits or UsageLimits.from_environment()
        return self

    def build(self) -> Pipeline[Any, Any]:
        """
        Build the pipeline.

        Returns:
            Configured Pipeline instance
        """
        return Pipeline(steps=self._steps)

    @property
    def usage_limits(self) -> UsageLimits | None:
        """Get the configured usage limits."""
        return self._usage_limits

    @property
    def governance(self) -> GovernanceConfig:
        """Get the governance configuration."""
        return self._governance
