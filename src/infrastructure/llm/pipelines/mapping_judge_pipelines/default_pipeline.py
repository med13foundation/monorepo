"""Default Flujo pipeline for Mapping Judge executions."""

from __future__ import annotations

from typing import TYPE_CHECKING

from flujo import Flujo, Pipeline
from flujo.domain.dsl import Step
from flujo.domain.models import UsageLimits as FlujoUsageLimits

from src.domain.agents.contexts.mapping_judge_context import MappingJudgeContext
from src.infrastructure.llm.config.governance import GovernanceConfig, UsageLimits
from src.infrastructure.llm.factories.mapping_judge_agent_factory import (
    create_mapping_judge_agent,
)

if TYPE_CHECKING:
    from flujo.state.backends.base import StateBackend

    from src.domain.agents.contracts.mapping_judge import MappingJudgeContract


def create_mapping_judge_pipeline(
    state_backend: StateBackend,
    *,
    model: str | None = None,
    usage_limits: UsageLimits | None = None,
) -> Flujo[str, MappingJudgeContract, MappingJudgeContext]:
    """Create a single-step mapping-judge pipeline."""
    governance = GovernanceConfig.from_environment()
    limits = usage_limits or governance.usage_limits
    agent = create_mapping_judge_agent(model=model)

    return Flujo(
        Pipeline(
            steps=[
                Step(
                    name="run_mapping_judge",
                    agent=agent,
                ),
            ],
        ),
        context_model=MappingJudgeContext,
        state_backend=state_backend,
        persist_state=True,
        usage_limits=_to_flujo_usage_limits(limits),
    )


def _to_flujo_usage_limits(limits: UsageLimits) -> FlujoUsageLimits:
    return FlujoUsageLimits(
        total_cost_usd_limit=limits.total_cost_usd,
        total_tokens_limit=limits.max_tokens,
    )
