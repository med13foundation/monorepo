"""PubMed graph-connection pipeline."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from flujo import Flujo, Pipeline, Step
from flujo.domain.agent_result import FlujoAgentResult
from flujo.domain.dsl import ConditionalStep, HumanInTheLoopStep
from flujo.domain.models import UsageLimits as FlujoUsageLimits

from src.domain.agents.contexts.graph_connection_context import GraphConnectionContext
from src.infrastructure.llm.config.governance import GovernanceConfig, UsageLimits
from src.infrastructure.llm.factories.graph_connection_agent_factory import (
    create_graph_connection_agent_for_source,
)
from src.infrastructure.llm.prompts.graph_connection.pubmed import (
    PUBMED_GRAPH_CONNECTION_DISCOVERY_SYSTEM_PROMPT,
    PUBMED_GRAPH_CONNECTION_SYNTHESIS_SYSTEM_PROMPT,
)

if TYPE_CHECKING:
    from flujo.state.backends.base import StateBackend

    from src.domain.agents.contracts.graph_connection import GraphConnectionContract


def _unwrap_agent_output(output: object) -> object:
    if isinstance(output, FlujoAgentResult):
        return output.output
    return output


def _check_graph_connection_confidence(  # noqa: C901, PLR0912
    output: object,
    _ctx: GraphConnectionContext | None,
) -> str:
    governance = GovernanceConfig.from_environment()
    threshold = governance.confidence_threshold
    resolved_output = _unwrap_agent_output(output)
    decision: str | None = None
    confidence_score = 0.0
    evidence: list[object] = []

    if isinstance(resolved_output, str):
        try:
            maybe_payload = json.loads(resolved_output)
        except json.JSONDecodeError:
            maybe_payload = None
        if isinstance(maybe_payload, dict):
            resolved_output = maybe_payload

    if isinstance(resolved_output, dict):
        raw_decision = resolved_output.get("decision")
        if isinstance(raw_decision, str):
            decision = raw_decision
        raw_confidence = resolved_output.get("confidence_score", 0.0)
        if isinstance(raw_confidence, int | float):
            confidence_score = float(raw_confidence)
        raw_evidence = resolved_output.get("evidence", [])
        if isinstance(raw_evidence, list):
            evidence = raw_evidence
    else:
        raw_decision = getattr(resolved_output, "decision", None)
        if isinstance(raw_decision, str):
            decision = raw_decision
        raw_confidence = getattr(resolved_output, "confidence_score", 0.0)
        if isinstance(raw_confidence, int | float):
            confidence_score = float(raw_confidence)
        raw_evidence = getattr(resolved_output, "evidence", [])
        if isinstance(raw_evidence, list):
            evidence = raw_evidence

    if decision == "escalate":
        return "escalate"
    if governance.require_evidence and not evidence:
        return "escalate"
    if governance.needs_human_review(confidence_score):
        return "escalate"
    return "proceed" if confidence_score >= threshold else "escalate"


def create_pubmed_graph_connection_pipeline(
    state_backend: StateBackend,
    *,
    model: str | None = None,
    use_governance: bool = True,
    usage_limits: UsageLimits | None = None,
    tools: list[object] | None = None,
) -> Flujo[str, GraphConnectionContract, GraphConnectionContext]:
    """Create a PubMed graph-connection pipeline."""
    governance = GovernanceConfig.from_environment()
    limits = usage_limits or governance.usage_limits
    discovery_agent = create_graph_connection_agent_for_source(
        "pubmed",
        model=model,
        system_prompt=PUBMED_GRAPH_CONNECTION_DISCOVERY_SYSTEM_PROMPT,
        tools=tools,
    )
    synthesis_agent = create_graph_connection_agent_for_source(
        "pubmed",
        model=model,
        system_prompt=PUBMED_GRAPH_CONNECTION_SYNTHESIS_SYSTEM_PROMPT,
        tools=tools,
    )

    steps: list[Step[object, object] | ConditionalStep[GraphConnectionContext]] = [
        Step(
            name="discover_pubmed_graph_connection_candidates",
            agent=discovery_agent,
        ),
        Step(
            name="synthesize_pubmed_graph_connections",
            agent=synthesis_agent,
        ),
    ]

    if use_governance:
        steps.append(
            ConditionalStep[GraphConnectionContext](
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
