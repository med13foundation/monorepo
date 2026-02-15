"""Default Flujo pipeline for Tier-2 content-enrichment executions."""

from __future__ import annotations

from typing import TYPE_CHECKING

from flujo import Flujo, Pipeline
from flujo.domain.dsl import GranularStep
from flujo.domain.models import UsageLimits as FlujoUsageLimits

from src.domain.agents.contexts.content_enrichment_context import (
    ContentEnrichmentContext,
)
from src.infrastructure.llm.config.governance import GovernanceConfig, UsageLimits
from src.infrastructure.llm.factories.content_enrichment_agent_factory import (
    create_content_enrichment_agent,
)

if TYPE_CHECKING:
    from flujo.state.backends.base import StateBackend

    from src.domain.agents.contracts.content_enrichment import (
        ContentEnrichmentContract,
    )


def create_content_enrichment_pipeline(
    state_backend: StateBackend,
    *,
    model: str | None = None,
    usage_limits: UsageLimits | None = None,
    tools: list[object] | None = None,
) -> Flujo[str, ContentEnrichmentContract, ContentEnrichmentContext]:
    """Create a content-enrichment pipeline with granular tool-calling durability."""
    governance = GovernanceConfig.from_environment()
    limits = usage_limits or governance.usage_limits
    agent = create_content_enrichment_agent(
        model=model,
        tools=tools,
    )
    return Flujo(
        Pipeline(
            steps=[
                GranularStep(
                    name="run_content_enrichment",
                    agent=agent,
                    enforce_idempotency=True,
                    history_max_tokens=8192,
                ),
            ],
        ),
        context_model=ContentEnrichmentContext,
        state_backend=state_backend,
        persist_state=True,
        usage_limits=_to_flujo_usage_limits(limits),
    )


def _to_flujo_usage_limits(limits: UsageLimits) -> FlujoUsageLimits:
    return FlujoUsageLimits(
        total_cost_usd_limit=limits.total_cost_usd,
        total_tokens_limit=limits.max_tokens,
    )
