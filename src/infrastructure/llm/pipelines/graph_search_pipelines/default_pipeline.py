"""Default Flujo pipeline for Graph Search agent executions."""

from __future__ import annotations

from typing import TYPE_CHECKING

from flujo import Flujo, Pipeline
from flujo.domain.dsl import GranularStep
from flujo.domain.models import UsageLimits as FlujoUsageLimits

from src.domain.agents.contexts.graph_search_context import GraphSearchContext
from src.infrastructure.llm.config.governance import GovernanceConfig, UsageLimits
from src.infrastructure.llm.factories.graph_search_agent_factory import (
    create_graph_search_agent,
)

if TYPE_CHECKING:
    from flujo.state.backends.base import StateBackend

    from src.domain.agents.contracts.graph_search import GraphSearchContract


def create_graph_search_pipeline(
    state_backend: StateBackend,
    *,
    model: str | None = None,
    usage_limits: UsageLimits | None = None,
    tools: list[object] | None = None,
) -> Flujo[str, GraphSearchContract, GraphSearchContext]:
    """Create graph-search pipeline with granular tool-calling durability."""
    governance = GovernanceConfig.from_environment()
    limits = usage_limits or governance.usage_limits
    agent = create_graph_search_agent(
        model=model,
        tools=tools,
    )

    return Flujo(
        Pipeline(
            steps=[
                GranularStep(
                    name="run_graph_search",
                    agent=agent,
                    enforce_idempotency=True,
                    history_max_tokens=8192,
                ),
            ],
        ),
        context_model=GraphSearchContext,
        state_backend=state_backend,
        persist_state=True,
        usage_limits=_to_flujo_usage_limits(limits),
    )


def _to_flujo_usage_limits(limits: UsageLimits) -> FlujoUsageLimits:
    return FlujoUsageLimits(
        total_cost_usd_limit=limits.total_cost_usd,
        total_tokens_limit=limits.max_tokens,
    )
