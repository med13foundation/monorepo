"""PubMed entity-recognition pipeline."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from flujo import Flujo, Pipeline
from flujo.domain.dsl import ConditionalStep, GranularStep, HumanInTheLoopStep
from flujo.domain.models import UsageLimits as FlujoUsageLimits

from src.domain.agents.contexts.entity_recognition_context import (
    EntityRecognitionContext,
)
from src.infrastructure.llm.config.governance import GovernanceConfig, UsageLimits
from src.infrastructure.llm.factories.entity_recognition_agent_factory import (
    create_entity_recognition_agent_for_source,
)

if TYPE_CHECKING:
    from flujo.state.backends.base import StateBackend

    from src.domain.agents.contracts.entity_recognition import EntityRecognitionContract

logger = logging.getLogger(__name__)


def _check_recognition_confidence(
    output: object,
    _ctx: EntityRecognitionContext | None,
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


def create_pubmed_entity_recognition_pipeline(
    state_backend: StateBackend,
    *,
    model: str | None = None,
    use_governance: bool = True,
    usage_limits: UsageLimits | None = None,
    tools: list[object] | None = None,
) -> Flujo[str, EntityRecognitionContract, EntityRecognitionContext]:
    """Create a PubMed entity-recognition pipeline."""
    governance = GovernanceConfig.from_environment()
    limits = usage_limits or governance.usage_limits
    agent = create_entity_recognition_agent_for_source(
        "pubmed",
        model=model,
        tools=tools,
    )

    steps: list[GranularStep | ConditionalStep[EntityRecognitionContext]] = [
        GranularStep(
            name="recognize_pubmed_entities",
            agent=agent,
            enforce_idempotency=True,
            history_max_tokens=8192,
        ),
    ]

    if use_governance:
        steps.append(
            ConditionalStep(
                name="entity_recognition_confidence_gate",
                condition_callable=_check_recognition_confidence,
                branches={
                    "escalate": Pipeline(
                        steps=[
                            HumanInTheLoopStep(
                                name="entity_recognition_human_review",
                                message_for_user=(
                                    "Entity-recognition confidence is below threshold. "
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
        context_model=EntityRecognitionContext,
        state_backend=state_backend,
        persist_state=True,
        usage_limits=_to_flujo_usage_limits(limits),
    )


def _to_flujo_usage_limits(limits: UsageLimits) -> FlujoUsageLimits:
    return FlujoUsageLimits(
        total_cost_usd_limit=limits.total_cost_usd,
        total_tokens_limit=limits.max_tokens,
    )
