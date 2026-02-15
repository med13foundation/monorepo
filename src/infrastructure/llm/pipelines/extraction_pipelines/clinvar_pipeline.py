"""ClinVar extraction pipeline."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from flujo import Flujo, Pipeline
from flujo.domain.dsl import ConditionalStep, GranularStep, HumanInTheLoopStep
from flujo.domain.models import UsageLimits as FlujoUsageLimits

from src.domain.agents.contexts.extraction_context import ExtractionContext
from src.infrastructure.llm.config.governance import GovernanceConfig, UsageLimits
from src.infrastructure.llm.factories.extraction_agent_factory import (
    create_extraction_agent_for_source,
)

if TYPE_CHECKING:
    from flujo.state.backends.base import StateBackend

    from src.domain.agents.contracts.extraction import ExtractionContract

logger = logging.getLogger(__name__)


def _check_extraction_confidence(
    output: object,
    _ctx: ExtractionContext | None,
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


def create_clinvar_extraction_pipeline(
    state_backend: StateBackend,
    *,
    model: str | None = None,
    use_governance: bool = True,
    usage_limits: UsageLimits | None = None,
    tools: list[object] | None = None,
) -> Flujo[str, ExtractionContract, ExtractionContext]:
    """Create a ClinVar extraction pipeline."""
    governance = GovernanceConfig.from_environment()
    limits = usage_limits or governance.usage_limits
    agent = create_extraction_agent_for_source(
        "clinvar",
        model=model,
        tools=tools,
    )

    steps: list[GranularStep | ConditionalStep[ExtractionContext]] = [
        GranularStep(
            name="extract_clinvar_facts",
            agent=agent,
            enforce_idempotency=True,
            history_max_tokens=8192,
        ),
    ]

    if use_governance:
        steps.append(
            ConditionalStep(
                name="extraction_confidence_gate",
                condition_callable=_check_extraction_confidence,
                branches={
                    "escalate": Pipeline(
                        steps=[
                            HumanInTheLoopStep(
                                name="extraction_human_review",
                                message_for_user=(
                                    "Extraction confidence is below threshold. "
                                    "Please review before writing to the graph."
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
        context_model=ExtractionContext,
        state_backend=state_backend,
        persist_state=True,
        usage_limits=_to_flujo_usage_limits(limits),
    )


def _to_flujo_usage_limits(limits: UsageLimits) -> FlujoUsageLimits:
    return FlujoUsageLimits(
        total_cost_usd_limit=limits.total_cost_usd,
        total_tokens_limit=limits.max_tokens,
    )
