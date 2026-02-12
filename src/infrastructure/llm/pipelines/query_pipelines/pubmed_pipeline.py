"""
PubMed query generation pipeline.

Creates a pipeline for generating PubMed Boolean queries with
governance patterns for confidence-based routing and usage limits.

Type Safety Note:
    This module uses `Any` types for Flujo Step/ConditionalStep generics.
    See base_pipeline.py for the rationale on this documented exception.

    The return type Flujo[str, QueryGenerationContract, QueryGenerationContext]
    is fully typed - only internal step lists use Any for Flujo compatibility.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from flujo import Flujo, Pipeline, Step
from flujo.domain.dsl import ConditionalStep, GranularStep, HumanInTheLoopStep
from flujo.domain.models import UsageLimits as FlujoUsageLimits

from src.domain.agents.contexts.query_context import QueryGenerationContext
from src.infrastructure.llm.config.governance import GovernanceConfig, UsageLimits
from src.infrastructure.llm.factories.query_agent_factory import (
    create_pubmed_query_agent,
)

if TYPE_CHECKING:
    from flujo.state.backends.base import StateBackend

    from src.domain.agents.contracts.query_generation import QueryGenerationContract

logger = logging.getLogger(__name__)


def _check_query_confidence(
    output: object,
    _ctx: object,
) -> str:
    """
    Check query generation confidence for routing.

    Routes to human review if:
    - Confidence is below threshold
    - Decision is "escalate"
    - Decision is "fallback" with low confidence
    - No evidence provided (if required)
    """
    governance = GovernanceConfig.from_environment()
    threshold = governance.confidence_threshold

    # Get attributes safely for type checker
    decision = getattr(output, "decision", None)
    confidence_score = getattr(output, "confidence_score", 0.0)
    evidence = getattr(output, "evidence", [])

    # Explicit escalation decision
    if decision == "escalate":
        logger.debug("Escalating: explicit escalation decision")
        return "escalate"

    # Fallback with low confidence should escalate
    if decision == "fallback" and confidence_score < threshold:
        logger.debug("Escalating: fallback with low confidence")
        return "escalate"

    # Check evidence requirement
    if governance.require_evidence and not evidence:
        logger.debug("Escalating: no evidence provided")
        return "escalate"

    # HITL threshold check
    if governance.needs_human_review(confidence_score):
        logger.debug("Escalating: below HITL threshold")
        return "escalate"

    # Normal confidence check
    result = "proceed" if confidence_score >= threshold else "escalate"
    logger.debug(
        "Confidence check: %s (%.2f vs %.2f)",
        result,
        confidence_score,
        threshold,
    )
    return result


def create_pubmed_query_pipeline(
    state_backend: StateBackend,
    *,
    model: str | None = None,
    use_governance: bool = True,
    use_granular: bool = False,  # Default to False - query gen is single-turn
    usage_limits: UsageLimits | None = None,
) -> Flujo[str, QueryGenerationContract, QueryGenerationContext]:
    """
    Create the PubMed query generation pipeline.

    Args:
        state_backend: Flujo state backend for persistence
        model: Optional model ID override
        use_governance: Include confidence-based governance gate
        use_granular: Use granular step for multi-turn durability (default False)
                      Note: Query generation is single-turn, so granular is not needed.
                      GranularStep is intended for multi-turn tool-use workflows.
        usage_limits: Optional usage limits (defaults to environment config)

    Returns:
        Configured Flujo runner for PubMed query generation
    """
    governance = GovernanceConfig.from_environment()
    limits = usage_limits or governance.usage_limits
    agent = create_pubmed_query_agent(model=model)

    # Build pipeline steps
    steps: list[Step[Any, Any] | GranularStep | ConditionalStep[Any]] = []

    # Create the main agent step
    # Note: Query generation is a single-turn task, so we use a regular Step.
    # GranularStep is for multi-turn workflows with tool use where each turn
    # needs to be persisted for crash recovery.
    if use_granular:
        # Use GranularStep for multi-turn durability (not typical for query gen)
        steps.append(
            GranularStep(
                name="generate_pubmed_query",
                agent=agent,
                enforce_idempotency=True,
                history_max_tokens=8192,
            ),
        )
    else:
        steps.append(
            Step(
                name="generate_pubmed_query",
                agent=agent,
            ),
        )

    if use_governance:
        governance_gate: ConditionalStep[Any] = ConditionalStep(
            name="query_confidence_gate",
            condition_callable=_check_query_confidence,
            branches={
                "escalate": Pipeline(
                    steps=[
                        HumanInTheLoopStep(
                            name="query_human_review",
                            message_for_user=(
                                "Query generation confidence is below threshold. "
                                "Please review the generated query before use."
                            ),
                        ),
                    ],
                ),
                "proceed": Pipeline(steps=[]),
            },
        )
        steps.append(governance_gate)

    # Build Flujo runner with usage limits
    runner_kwargs: dict[str, object] = {
        "context_model": QueryGenerationContext,
        "state_backend": state_backend,
        "persist_state": True,
        "usage_limits": _to_flujo_usage_limits(limits),
    }

    if limits.max_turns is not None:
        logger.debug(
            "UsageLimits.max_turns=%s is ignored by Flujo 0.6.3; "
            "controlled by max_tokens/cost only.",
            limits.max_turns,
        )

    return Flujo(
        Pipeline(steps=steps),
        **runner_kwargs,  # type: ignore[arg-type]
    )


def _to_flujo_usage_limits(
    limits: UsageLimits,
) -> FlujoUsageLimits:
    """
    Convert internal UsageLimits to Flujo UsageLimits.

    Note:
    - Flujo expects total_cost_usd_limit and total_tokens_limit.
    - max_turns is tracked by domain policy only and is not mapped.
    """
    return FlujoUsageLimits(
        total_cost_usd_limit=limits.total_cost_usd,
        total_tokens_limit=limits.max_tokens,
    )
