"""Extraction relation-policy pipeline."""

from __future__ import annotations

from typing import TYPE_CHECKING

from flujo import Flujo, Pipeline
from flujo.domain.dsl import GranularStep
from flujo.domain.models import UsageLimits as FlujoUsageLimits

from src.domain.agents.contexts.extraction_policy_context import ExtractionPolicyContext
from src.infrastructure.llm.config.governance import GovernanceConfig, UsageLimits
from src.infrastructure.llm.factories.extraction_policy_agent_factory import (
    create_extraction_policy_agent,
)

if TYPE_CHECKING:
    from flujo.state.backends.base import StateBackend

    from src.domain.agents.contracts.extraction_policy import ExtractionPolicyContract


def create_extraction_policy_pipeline(
    state_backend: StateBackend,
    *,
    model: str | None = None,
    usage_limits: UsageLimits | None = None,
) -> Flujo[str, ExtractionPolicyContract, ExtractionPolicyContext]:
    """Create a single-step policy proposal pipeline."""
    governance = GovernanceConfig.from_environment()
    limits = usage_limits or governance.usage_limits
    agent = create_extraction_policy_agent(model=model)

    return Flujo(
        Pipeline(
            steps=[
                GranularStep(
                    name="propose_relation_policy",
                    agent=agent,
                    enforce_idempotency=True,
                    history_max_tokens=8192,
                ),
            ],
        ),
        context_model=ExtractionPolicyContext,
        state_backend=state_backend,
        persist_state=True,
        usage_limits=_to_flujo_usage_limits(limits),
    )


def _to_flujo_usage_limits(limits: UsageLimits) -> FlujoUsageLimits:
    return FlujoUsageLimits(
        total_cost_usd_limit=limits.total_cost_usd,
        total_tokens_limit=limits.max_tokens,
    )


__all__ = ["create_extraction_policy_pipeline"]
