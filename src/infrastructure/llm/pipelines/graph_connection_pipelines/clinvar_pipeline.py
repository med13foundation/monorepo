"""ClinVar graph-connection pipeline."""

from __future__ import annotations

from typing import TYPE_CHECKING

from flujo import Flujo, Pipeline
from flujo.domain.dsl import ConditionalStep, GranularStep, HumanInTheLoopStep
from flujo.domain.models import UsageLimits as FlujoUsageLimits

from src.domain.agents.contexts.graph_connection_context import GraphConnectionContext
from src.infrastructure.llm.config.governance import GovernanceConfig, UsageLimits
from src.infrastructure.llm.factories.graph_connection_agent_factory import (
    create_graph_connection_agent_for_source,
)

if TYPE_CHECKING:
    from flujo.state.backends.base import StateBackend

    from src.domain.agents.contracts.graph_connection import GraphConnectionContract


def _check_graph_connection_confidence(
    output: object,
    _ctx: GraphConnectionContext | None,
) -> str:
    governance = GovernanceConfig.from_environment()
    threshold = governance.confidence_threshold
    decision = getattr(output, "decision", None)
    confidence_score = getattr(output, "confidence_score", 0.0)
    evidence = getattr(output, "evidence", [])

    if decision == "escalate":
        return "escalate"
    if governance.require_evidence and not evidence:
        return "escalate"
    if governance.needs_human_review(confidence_score):
        return "escalate"
    return "proceed" if confidence_score >= threshold else "escalate"


def create_clinvar_graph_connection_pipeline(
    state_backend: StateBackend,
    *,
    model: str | None = None,
    use_governance: bool = True,
    usage_limits: UsageLimits | None = None,
    tools: list[object] | None = None,
) -> Flujo[str, GraphConnectionContract, GraphConnectionContext]:
    """Create a ClinVar graph-connection pipeline."""
    governance = GovernanceConfig.from_environment()
    limits = usage_limits or governance.usage_limits
    agent = create_graph_connection_agent_for_source(
        "clinvar",
        model=model,
        tools=tools,
    )

    steps: list[GranularStep | ConditionalStep[GraphConnectionContext]] = [
        GranularStep(
            name="discover_graph_connections",
            agent=agent,
            enforce_idempotency=True,
            history_max_tokens=8192,
        ),
    ]

    if use_governance:
        steps.append(
            ConditionalStep(
                name="graph_connection_confidence_gate",
                condition_callable=_check_graph_connection_confidence,
                branches={
                    "escalate": Pipeline(
                        steps=[
                            HumanInTheLoopStep(
                                name="graph_connection_human_review",
                                message_for_user=(
                                    "Graph-connection confidence is below threshold. "
                                    "Please review before writing relations."
                                ),
                            ),
                        ],
                    ),
                    "proceed": Pipeline(steps=[]),
                },
            ),
        )

    return Flujo(
        Pipeline(steps=steps),
        context_model=GraphConnectionContext,
        state_backend=state_backend,
        persist_state=True,
        usage_limits=_to_flujo_usage_limits(limits),
    )


def _to_flujo_usage_limits(limits: UsageLimits) -> FlujoUsageLimits:
    return FlujoUsageLimits(
        total_cost_usd_limit=limits.total_cost_usd,
        total_tokens_limit=limits.max_tokens,
    )
